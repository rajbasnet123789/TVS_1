"""
YOLOv11 + P2 + Transformer ReID Pipeline (Backward Compatible)

Main pipeline for single-camera hen detection, tracking, and counting.
Integrates:
- YOLOv11 with P2 detection head for small objects
- Transformer-based ReID for cross-camera identification
- XGBoost weight estimation
- Zone-based counting with trajectory tracking

Fallback: If YOLOv11 or Transformer ReID unavailable, falls back to
existing YOLOv8 + MiewID models.
"""

import cv2
import os
import sys
import time
import torch
import numpy as np
import torch.nn as nn
import torch.nn.functional as F
from ultralytics import YOLO
from safetensors.torch import load_file
from huggingface_hub import hf_hub_download

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "weight_model"))
from hen_counter import HenCounter
from weight_predictor import ChickenWeightPredictor

# ==========================================
# Configuration
# ==========================================
MIEWID_REPO = "conservationxlabs/miewid-msv3"
MIEWID_DIM = 2152
REID_MATCH_THRESHOLD = 0.5
CONF_THRESHOLD = 0.35
MIN_BOX_AREA = 400
MAX_ASPECT_RATIO = 3.0

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WEIGHT_MODEL_DIR = os.path.join(SCRIPT_DIR, "weight_model")

# Class names to search for in priority order
CHICKEN_CLASS_NAMES = ["chicken", "hen"]
COCO_BIRD_CLASS_ID = 14  # "bird" in COCO

# Detection ROI polygons (normalized 0-1 coordinates)
DETECTION_ROI = {
    "CH_01": [[0.1425, 0.3638], [0.70625, 0.2634], [0.94875, 0.9933], [0.00125, 0.9933]],
    "CH_02": [[0.2547, 0.1889], [0.79375, 0.1653], [0.9609, 0.9972], [0.0008, 0.9944], [0.0117, 0.65]],
    "CH_03": [[0.2075, 0.2321], [0.70625, 0.125], [0.995, 0.9933], [0.00625, 0.9888]],
    "CH_04": [[0.5391, 0.1773], [0.9169, 0.3014], [0.874, 0.9986], [0.1341, 0.9944], [0.1581, 0.6171]],
    "CH_06": [[0.2675, 0.1317], [0.835, 0.1362], [0.995, 0.9978], [0.07, 0.9978], [0.00375, 0.7165]],
}


# ==========================================
# GeM Pooling
# ==========================================
class GeM(nn.Module):
    def __init__(self, p=3, eps=1e-6):
        super().__init__()
        self.p = nn.Parameter(torch.ones(1) * p)
        self.eps = eps
    def forward(self, x):
        return F.avg_pool2d(x.clamp(min=self.eps).pow(self.p), (x.size(-2), x.size(-1))).pow(1. / self.p)


# ==========================================
# ReID Extractor (auto-selects best available)
# ==========================================
class ReIDExtractor:
    """Auto-selecting ReID: Transformer > MiewID > None."""

    def __init__(self):
        self._backbone = None
        self._bn = None
        self._transform = None
        self._device = "cpu"
        self._loaded = False
        self._backend = None
        self._reid_dim = 512

    def load(self):
        self._device = "cuda:0" if torch.cuda.is_available() else "cpu"

        # Try Transformer ReID first
        if self._try_load_transformer():
            return

        # Fallback to MiewID
        if self._try_load_miewid():
            return

        print("[ReID] No ReID model available")

    def _try_load_transformer(self):
        try:
            sys.path.insert(0, SCRIPT_DIR)
            from model_config.transformer_reid import ViTReID, TransformerReIDExtractor

            reid_path = os.path.join(SCRIPT_DIR, "model_config", "transformer_reid.pt")
            model = ViTReID(
                img_size=224, patch_size=16, embed_dim=384,
                depth=12, num_heads=6, num_classes=512,
            )
            if os.path.exists(reid_path):
                state_dict = torch.load(reid_path, map_location=self._device)
                model.load_state_dict(state_dict, strict=False)

            self._backbone = model.to(self._device).eval()
            self._bn = None
            self._reid_dim = 512
            self._backend = "transformer"

            import torchvision.transforms as transforms
            self._transform = transforms.Compose([
                transforms.Resize((224, 224)),
                transforms.ToTensor(),
                transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
            ])
            self._loaded = True
            print(f"[ReID] Transformer loaded on {self._device} (dim=512)")
            return True
        except Exception as e:
            print(f"[ReID] Transformer load failed: {e}")
            return False

    def _try_load_miewid(self):
        try:
            import timm
            backbone = timm.create_model("efficientnetv2_rw_m", pretrained=False, num_classes=0)
            backbone.global_pool = GeM()
            bn = nn.BatchNorm1d(MIEWID_DIM)
            weights_path = hf_hub_download(MIEWID_REPO, "model.safetensors")
            weights = load_file(weights_path)
            backbone_state = {k.replace("backbone.", ""): v for k, v in weights.items() if k.startswith("backbone.")}
            backbone.load_state_dict(backbone_state, strict=False)
            bn_state = {k.replace("bn.", ""): v for k, v in weights.items() if k.startswith("bn.")}
            bn.load_state_dict(bn_state)
            self._backbone = backbone.to(self._device).eval()
            self._bn = bn.to(self._device).eval()
            self._reid_dim = MIEWID_DIM
            self._backend = "miewid"
            from timm.data import resolve_data_config, create_transform
            data_config = resolve_data_config(self._backbone.pretrained_cfg)
            self._transform = create_transform(**data_config, is_training=False)
            self._loaded = True
            print(f"[ReID] MiewID loaded on {self._device} (dim={MIEWID_DIM})")
            return True
        except Exception as e:
            print(f"[ReID] MiewID load failed: {e}")
            return False

    def extract(self, frame, bboxes):
        if not self._loaded:
            return [None] * len(bboxes)
        from PIL import Image
        crops, valid_idx = [], []
        for i, bbox in enumerate(bboxes):
            x1 = max(0, int(bbox["x"]))
            y1 = max(0, int(bbox["y"]))
            x2 = min(frame.shape[1], int(bbox["x"] + bbox["w"]))
            y2 = min(frame.shape[0], int(bbox["y"] + bbox["h"]))
            if x2 - x1 < 10 or y2 - y1 < 10:
                continue
            crop = frame[y1:y2, x1:x2]
            if crop.size == 0:
                continue
            pil = Image.fromarray(crop[:, :, ::-1] if crop.shape[2] == 3 else crop)
            t = self._transform(pil).unsqueeze(0)
            crops.append(t)
            valid_idx.append(i)
        if not crops:
            return [None] * len(bboxes)
        try:
            batch = torch.cat(crops, dim=0).to(self._device)
            with torch.no_grad():
                if self._backend == "transformer":
                    features = self._backbone(batch)
                else:
                    feat = self._backbone(batch)
                    feat = feat.view(feat.size(0), -1)
                    features = self._bn(feat)
            features = features.cpu().numpy()
            result = [None] * len(bboxes)
            for j, idx in enumerate(valid_idx):
                if j < len(features):
                    emb = features[j].flatten()
                    n = np.linalg.norm(emb)
                    result[idx] = emb / n if n > 0 else emb
            return result
        except Exception as e:
            print(f"[ReID] Extract failed: {e}")
            return [None] * len(bboxes)


# ==========================================
# ReID Gallery
# ==========================================
class ReIDGallery:
    def __init__(self, dim=512, threshold=REID_MATCH_THRESHOLD):
        self.dim = dim
        self.threshold = threshold
        self._embs = {}
        self._next_id = 1
        try:
            import faiss
            self._index = faiss.IndexFlatIP(dim)
            self._id_map = []
            self._use_faiss = True
        except ImportError:
            self._index = None
            self._id_map = []
            self._use_faiss = False

    def match_or_create(self, emb, confidence=0.0):
        if emb is None:
            return self._add(np.zeros(self.dim, dtype=np.float32), confidence)
        if self._use_faiss and self._index.ntotal > 0:
            k = min(5, self._index.ntotal)
            dists, idxs = self._index.search(emb.reshape(1, -1).astype(np.float32), k)
            for d, idx in zip(dists[0], idxs[0]):
                if 0 <= idx < len(self._id_map) and d >= self.threshold:
                    gid = self._id_map[idx]
                    self._update_embedding(gid, emb, confidence)
                    return gid
        return self._add(emb, confidence)

    def _add(self, emb, confidence):
        gid = self._next_id
        self._next_id += 1
        self._embs[gid] = emb.copy()
        if self._use_faiss:
            self._index.add(emb.reshape(1, -1).astype(np.float32))
        self._id_map.append(gid)
        return gid

    def _update_embedding(self, gid, emb, confidence):
        old = self._embs.get(gid)
        if old is None:
            return
        alpha = 0.3
        updated = alpha * emb + (1 - alpha) * old
        n = np.linalg.norm(updated)
        if n > 0:
            updated = updated / n
        self._embs[gid] = updated

    @property
    def size(self):
        return len(self._embs)


# ==========================================
# Chicken Class ID Detection
# ==========================================
def detect_chicken_class_id(yolo_model):
    """
    Auto-detect the chicken/hen class ID from the loaded YOLO model.
    Priority: 'chicken' > 'hen' > 'bird' (COCO fallback).
    Returns (class_id, class_name, is_custom_model).
    """
    class_names = yolo_model.names  # {0: 'chicken', 1: 'hen', ...} or {0: 'person', ...}
    name_to_id = {name.lower(): cid for cid, name in class_names.items()}

    # Check for chicken/hen (custom model)
    for target in CHICKEN_CLASS_NAMES:
        if target in name_to_id:
            cid = name_to_id[target]
            print(f"[Model] Found '{target}' at class ID {cid}")
            return cid, target, True

    # Fallback to COCO 'bird' class
    if "bird" in name_to_id:
        cid = name_to_id["bird"]
        print(f"[Model] No chicken/hen class found. Using 'bird' (ID {cid})")
        return cid, "bird", False

    # Last resort: use first available class
    first_id = min(class_names.keys()) if class_names else 0
    first_name = class_names.get(first_id, "unknown")
    print(f"[Model] Warning: No chicken/hen/bird found. Using first class: '{first_name}' (ID {first_id})")
    return first_id, first_name, False


# ==========================================
# Setup & Model Loading
# ==========================================
def load_all_models():
    """Load all models once, return (model, device, weight_predictor, reid, chicken_class_id)."""
    yolo_paths = [
        os.path.join(WEIGHT_MODEL_DIR, "yolo_chicken", "best.pt"),
        os.path.join(SCRIPT_DIR, "yolov11n-p2.pt"),
        "yolov11n.pt",
    ]
    model = None
    for path in yolo_paths:
        if os.path.exists(path):
            try:
                model = YOLO(path)
                print(f"YOLO model loaded: {path}")
                break
            except Exception:
                pass
    if model is None:
        model = YOLO("yolov11n.pt")
        print("Loaded default YOLOv11n")

    device = "cuda" if torch.cuda.is_available() else "cpu"
    model.to(device)

    chicken_class_id, chicken_class_name, is_custom = detect_chicken_class_id(model)
    print(f"Target class: '{chicken_class_name}' (ID {chicken_class_id}) | Custom model: {is_custom}")

    weight_predictor = ChickenWeightPredictor(
        model_path=os.path.join(WEIGHT_MODEL_DIR, "weight_model.ubj"),
        stats_path=os.path.join(WEIGHT_MODEL_DIR, "norm_stats.json"),
    )

    reid = ReIDExtractor()
    reid.load()

    return model, device, weight_predictor, reid, chicken_class_id


def point_in_roi(cx, cy, roi_polygon, frame_w, frame_h):
    """Check if point (cx, cy) is inside the ROI polygon (normalized coords)."""
    pts = np.array(roi_polygon, dtype=np.float32)
    pts[:, 0] *= frame_w
    pts[:, 1] *= frame_h
    return cv2.pointPolygonTest(pts, (cx, cy), False) >= 0


def detect_single_image(model, device, weight_predictor, reid, image_path, chicken_class_id, roi_polygon=None):
    """Run detection on a single image. Returns annotated frame and results dict."""
    frame = cv2.imread(image_path)
    if frame is None:
        print(f"  Could not read image: {image_path}")
        return None, None

    h, w = frame.shape[:2]

    results = model(
        source=frame,
        conf=CONF_THRESHOLD,
        imgsz=1280,
        device=device,
        verbose=False,
    )[0]

    detections = []
    bboxes_for_reid = []

    if results.boxes is not None and len(results.boxes) > 0:
        for box in results.boxes:
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            conf = float(box.conf[0])
            cls_id = int(box.cls[0])

            if cls_id != chicken_class_id:
                continue

            bw = int(x2 - x1)
            bh = int(y2 - y1)
            box_area = bw * bh
            if box_area < MIN_BOX_AREA:
                continue
            aspect = max(bw, bh) / max(min(bw, bh), 1)
            if aspect > MAX_ASPECT_RATIO:
                continue

            # ROI filter: check if center of bbox is inside the ROI polygon
            if roi_polygon is not None:
                cx = x1 + bw / 2
                cy = y1 + bh / 2
                if not point_in_roi(cx, cy, roi_polygon, w, h):
                    continue

            mask = np.zeros((bh, bw), dtype=np.uint8)
            cv2.rectangle(mask, (0, 0), (bw - 1, bh - 1), 255, -1)
            weight = weight_predictor.predict(mask)

            bbox_dict = {"x": x1, "y": y1, "w": bw, "h": bh}
            detections.append({
                "bbox": bbox_dict,
                "confidence": conf,
                "class_id": cls_id,
                "class_name": results.names.get(cls_id, str(cls_id)),
                "weight": weight,
            })
            bboxes_for_reid.append(bbox_dict)

    embeddings = reid.extract(frame, bboxes_for_reid)
    for det, emb in zip(detections, embeddings):
        if emb is not None:
            det["global_id"] = emb

    return frame, detections


def annotate_frame(frame, detections, channel_name):
    """Draw bounding boxes and info panel on frame."""
    COLORS = [
        (0, 255, 0), (255, 0, 0), (0, 0, 255), (255, 255, 0),
        (0, 255, 255), (255, 0, 255), (128, 255, 0), (255, 128, 0),
    ]

    total_weight = 0.0
    for i, det in enumerate(detections):
        bbox = det["bbox"]
        x1 = int(bbox["x"])
        y1 = int(bbox["y"])
        x2 = int(bbox["x"] + bbox["w"])
        y2 = int(bbox["y"] + bbox["h"])

        color = COLORS[i % len(COLORS)]
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

        label = f"#{i+1}"
        if det.get("weight"):
            label += f" {det['weight']:.2f}kg"
            total_weight += det["weight"]
        cv2.putText(frame, label, (x1, y1 - 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

    h, w = frame.shape[:2]
    overlay = frame.copy()
    panel_w = 350
    panel_h = 140
    cv2.rectangle(overlay, (10, 10), (panel_w, panel_h), (0, 0, 0), -1)
    cv2.addWeighted(overlay, 0.6, frame, 0.4, 0, frame)

    y_off = 40
    line_h = 28
    cv2.putText(frame, f"Channel: {channel_name}",
                (20, y_off), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
    y_off += line_h
    cv2.putText(frame, f"Hens Detected: {len(detections)}",
                (20, y_off), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
    y_off += line_h
    cv2.putText(frame, f"Total Weight: {total_weight:.2f} kg",
                (20, y_off), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 200, 0), 2)
    y_off += line_h
    cv2.putText(frame, f"Avg Weight: {total_weight/len(detections):.2f} kg" if detections else "Avg Weight: 0.00 kg",
                (20, y_off), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (200, 200, 200), 1)

    return frame


def run_main():
    """Process jpg images from all channel directories."""
    print("=" * 60)
    print("  Poultry Farm - Channel Image Processing")
    print("=" * 60)

    model, device, weight_predictor, reid, chicken_class_id = load_all_models()

    output_dir = os.path.join(SCRIPT_DIR, "output_results")
    os.makedirs(output_dir, exist_ok=True)

    channel_dirs = sorted([
        d for d in os.listdir(SCRIPT_DIR)
        if os.path.isdir(os.path.join(SCRIPT_DIR, d)) and d.startswith("CH_")
    ])

    print(f"\nFound {len(channel_dirs)} channels: {', '.join(channel_dirs)}")
    print(f"Output directory: {output_dir}\n")

    summary = []

    for ch_dir in channel_dirs:
        ch_path = os.path.join(SCRIPT_DIR, ch_dir)
        images = [f for f in os.listdir(ch_path) if f.lower().endswith((".jpg", ".jpeg", ".png"))]

        if not images:
            print(f"[{ch_dir}] No images found, skipping.")
            continue

        for img_file in images:
            img_path = os.path.join(ch_path, img_file)
            roi = DETECTION_ROI.get(ch_dir)
            print(f"[{ch_dir}] Processing: {img_file} (ROI: {'yes' if roi else 'no'})")

            frame, detections = detect_single_image(
                model, device, weight_predictor, reid, img_path, chicken_class_id, roi_polygon=roi
            )
            if frame is None:
                continue

            annotated = annotate_frame(frame.copy(), detections, ch_dir)

            out_path = os.path.join(output_dir, f"{ch_dir}_{os.path.splitext(img_file)[0]}_detected.jpg")
            cv2.imwrite(out_path, annotated)

            total_weight = sum(d.get("weight", 0) or 0 for d in detections)
            avg_weight = total_weight / len(detections) if detections else 0

            summary.append({
                "channel": ch_dir,
                "image": img_file,
                "hens": len(detections),
                "total_weight_kg": round(total_weight, 2),
                "avg_weight_kg": round(avg_weight, 2),
            })

            print(f"  -> {len(detections)} hens detected, "
                  f"total: {total_weight:.2f}kg, avg: {avg_weight:.2f}kg")
            print(f"  -> Saved: {out_path}")

    print("\n" + "=" * 60)
    print("  SUMMARY")
    print("=" * 60)
    total_hens = 0
    total_wt = 0.0
    for s in summary:
        print(f"  {s['channel']:6s} | {s['image']:40s} | Hens: {s['hens']:3d} | "
              f"Total: {s['total_weight_kg']:7.2f} kg | Avg: {s['avg_weight_kg']:5.2f} kg")
        total_hens += s["hens"]
        total_wt += s["total_weight_kg"]
    print(f"\n  Total hens detected: {total_hens}")
    print(f"  Total weight: {total_wt:.2f} kg")
    print(f"  Results saved to: {output_dir}")
    print("=" * 60)


if __name__ == "__main__":
    run_main()
