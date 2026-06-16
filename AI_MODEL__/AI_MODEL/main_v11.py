"""
YOLOv11 + P2 + Transformer ReID + MSFN Pipeline

Main pipeline for single-camera hen detection, tracking, and counting
with the new architecture. Integrates:
- YOLOv11 with P2 detection head for small objects
- Transformer-based ReID for cross-camera identification
- MSFN-enhanced detection for long-range accuracy
- XGBoost weight estimation
- Zone-based counting with trajectory tracking
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

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "weight_model"))
from hen_counter import HenCounter
from weight_predictor import ChickenWeightPredictor

# ==========================================
# Model Configuration
# ==========================================
CONF_THRESHOLD = 0.35
MIN_BOX_AREA = 400
MAX_ASPECT_RATIO = 3.0

# Class names to search for in priority order
CHICKEN_CLASS_NAMES = ["chicken", "hen"]
COCO_BIRD_CLASS_ID = 14  # "bird" in COCO

# Model paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
YOLO_MODEL_PATH = os.path.join(SCRIPT_DIR, "weight_model", "yolo_chicken", "best.pt")
WEIGHT_MODEL_PATH = os.path.join(SCRIPT_DIR, "weight_model", "weight_model.ubj")
NORM_STATS_PATH = os.path.join(SCRIPT_DIR, "weight_model", "norm_stats.json")
REID_MODEL_PATH = os.path.join(SCRIPT_DIR, "model_config", "transformer_reid.pt")


# ==========================================
# Transformer ReID (from model_config)
# ==========================================
from model_config.transformer_reid import TransformerReIDExtractor


# ==========================================
# Chicken Class ID Detection
# ==========================================
def detect_chicken_class_id(yolo_model):
    """
    Auto-detect the chicken/hen class ID from the loaded YOLO model.
    Priority: 'chicken' > 'hen' > 'bird' (COCO fallback).
    Returns (class_id, class_name, is_custom_model).
    """
    class_names = yolo_model.names
    name_to_id = {name.lower(): cid for cid, name in class_names.items()}

    for target in CHICKEN_CLASS_NAMES:
        if target in name_to_id:
            cid = name_to_id[target]
            print(f"[Model] Found '{target}' at class ID {cid}")
            return cid, target, True

    if "bird" in name_to_id:
        cid = name_to_id["bird"]
        print(f"[Model] No chicken/hen class found. Using 'bird' (ID {cid})")
        return cid, "bird", False

    first_id = min(class_names.keys()) if class_names else 0
    first_name = class_names.get(first_id, "unknown")
    print(f"[Model] Warning: No chicken/hen/bird found. Using first class: '{first_name}' (ID {first_id})")
    return first_id, first_name, False


class ReIDGallery:
    """FAISS-based embedding gallery for ReID matching."""

    def __init__(self, dim=512, threshold=0.5):
        self.dim = dim
        self.threshold = threshold
        self._embs = {}
        self._next_id = 1
        try:
            import faiss
            self._index = faiss.IndexFlatIP(dim)
            self._use_faiss = True
        except ImportError:
            self._index = None
            self._use_faiss = False
        self._id_map = []

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
# Setup & Model Loading
# ==========================================
def load_models():
    """Load all models for the pipeline."""
    print("=" * 60)
    print("  YOLOv11 + P2 + Transformer ReID Pipeline")
    print("=" * 60)

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Device: {device}")

    # Load YOLO model — prioritize custom fine-tuned model first
    yolo_paths = [
        YOLO_MODEL_PATH,                                          # Custom fine-tuned (priority)
        os.path.join(SCRIPT_DIR, "yolov11n-p2.pt"),               # YOLOv11 with P2 head
        "yolov11n.pt",                                             # Generic YOLOv11n
    ]

    model = None
    for path in yolo_paths:
        if os.path.exists(path):
            try:
                model = YOLO(path)
                print(f"YOLO model loaded: {path}")
                break
            except Exception as e:
                print(f"Failed to load {path}: {e}")

    if model is None:
        print("Loading default YOLOv11n...")
        model = YOLO("yolov11n.pt")

    model.to(device)

    # Auto-detect chicken class ID from the loaded model
    chicken_class_id, chicken_class_name, is_custom = detect_chicken_class_id(model)
    print(f"Target class: '{chicken_class_name}' (ID {chicken_class_id}) | Custom model: {is_custom}")

    # Load weight predictor
    weight_predictor = ChickenWeightPredictor(
        model_path=WEIGHT_MODEL_PATH,
        stats_path=NORM_STATS_PATH,
    )
    print("Weight predictor loaded")

    # Load Transformer ReID
    reid = TransformerReIDExtractor(device=device)
    reid.load(model_path=REID_MODEL_PATH)
    gallery = ReIDGallery(dim=512, threshold=0.5)

    # Load hen counter
    hen_counter = HenCounter(640, 480)

    print("=" * 60)
    print("  All models loaded successfully!")
    print("=" * 60)

    return model, device, weight_predictor, reid, gallery, hen_counter, chicken_class_id


# ==========================================
# Visualization Helpers
# ==========================================
COLORS = [
    (0, 255, 0), (255, 0, 0), (0, 0, 255), (255, 255, 0),
    (0, 255, 255), (255, 0, 255), (128, 255, 0), (255, 128, 0),
    (0, 128, 255), (255, 255, 128), (128, 0, 255), (255, 128, 128),
]


def draw_zones(frame, counter, show_zones):
    if not show_zones:
        return
    overlay = frame.copy()
    for zone in counter.counter._zones:
        pts = np.array(zone.polygon, dtype=np.int32)
        cv2.fillPoly(overlay, [pts], (0, 255, 0, 30))
        cv2.polylines(overlay, [pts], True, (0, 255, 0), 1)
        cx = int(np.mean([p[0] for p in zone.polygon]))
        cy = int(np.mean([p[1] for p in zone.polygon]))
        cv2.putText(overlay, zone.name, (cx - 30, cy),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
    cv2.addWeighted(overlay, 0.3, frame, 0.7, 0, frame)


def draw_trajectories(frame, trajectories, active_hens):
    for track_id, points in trajectories.items():
        if len(points) < 2:
            continue
        pts = np.array(points[-30:], dtype=np.int32)
        for i in range(1, len(pts)):
            thickness = int(1 + (i / len(pts)) * 2)
            alpha = i / len(pts)
            color = (0, int(150 * alpha + 50), int(255 * (1 - alpha)))
            cv2.line(frame, tuple(pts[i - 1]), tuple(pts[i]), color, thickness)


def draw_info_panel(frame, frame_result, gallery_size, show_zones):
    h, w = frame.shape[:2]
    overlay = frame.copy()
    panel_w = 420
    panel_h = 220
    cv2.rectangle(overlay, (10, 10), (panel_w, panel_h), (0, 0, 0), -1)
    cv2.addWeighted(overlay, 0.6, frame, 0.4, 0, frame)

    y_off = 40
    line_h = 30
    cv2.putText(frame, f"Architecture: YOLOv11 + P2 + Transformer ReID",
                (20, y_off), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)
    y_off += line_h
    cv2.putText(frame, f"Visible Now: {frame_result['current_count']}",
                (20, y_off), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 0), 2)
    y_off += line_h
    cv2.putText(frame, f"Unique Hens: {frame_result['unique_count']}",
                (20, y_off), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 200, 0), 2)
    y_off += line_h
    cv2.putText(frame, f"Total Seen: {frame_result['total_seen']}",
                (20, y_off), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 200, 255), 2)
    y_off += line_h
    cv2.putText(frame, f"Gallery IDs: {gallery_size}",
                (20, y_off), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (200, 100, 255), 2)
    y_off += line_h
    zone_text = " | ".join(f"{k}:{v}" for k, v in frame_result["zone_counts"].items() if v > 0)
    if zone_text:
        cv2.putText(frame, f"Zones: {zone_text}",
                    (20, y_off), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1)
        y_off += line_h
    cv2.putText(frame, "q:quit r:reset z:zones",
                (20, y_off), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (150, 150, 150), 1)


# ==========================================
# Main Pipeline
# ==========================================
def run_main():
    model, device, weight_predictor, reid, gallery, hen_counter, chicken_class_id = load_models()

    video_path = r"C:\Users\wwwra\Downloads\WhatsApp Video 2026-06-10 at 11.28.32 AM.mp4"
    if not os.path.exists(video_path):
        print(f"Error: Video file not found at {video_path}")
        return

    cap = cv2.VideoCapture(video_path)
    frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    hen_counter = HenCounter(frame_width, frame_height)

    window_name = "Poultry Farm - YOLOv11 + P2 + Transformer ReID"
    cv2.namedWindow(window_name, cv2.WINDOW_AUTOSIZE)

    print(f"Resolution: {frame_width}x{frame_height}")
    print("Press 'q' to quit, 'r' to reset counter, 'z' to toggle zones.")

    show_zones = True
    frame_count = 0
    fps_start = time.time()

    while cap.isOpened():
        success, frame = cap.read()
        if not success:
            break

        frame_count += 1

        # YOLO detection with tracking
        results = model.track(
            source=frame,
            conf=CONF_THRESHOLD,
            imgsz=1280,
            device=device,
            verbose=False,
            tracker="botsort_custom.yaml",
            persist=True,
        )[0]

        detections = []
        track_ids = []
        bboxes_for_reid = []

        if results.boxes is not None and len(results.boxes) > 0:
            for box in results.boxes:
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                conf = float(box.conf[0])
                cls_id = int(box.cls[0])
                tid = int(box.id[0]) if box.id is not None else None

                # Filter: only process detections matching the target class
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
                track_ids.append(tid)
                bboxes_for_reid.append(bbox_dict)

        # Transformer ReID embedding extraction
        embeddings = reid.extract(frame, bboxes_for_reid)

        # Global ID assignment
        for det, emb in zip(detections, embeddings):
            if emb is not None:
                det["global_id"] = gallery.match_or_create(emb, det["confidence"])

        # Zone-based counting
        frame_result = hen_counter.process_frame(detections, track_ids)

        # Visualization
        draw_zones(frame, hen_counter, show_zones)
        draw_trajectories(frame, hen_counter.get_trajectories(), hen_counter._active_hens)

        for det in frame_result["detections"]:
            bbox = det["bbox"]
            x1 = int(bbox["x"])
            y1 = int(bbox["y"])
            x2 = int(bbox["x"] + bbox["w"])
            y2 = int(bbox["y"] + bbox["h"])

            gid = det.get("global_id")
            color = COLORS[gid % len(COLORS)] if gid else (0, 255, 0)
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

        draw_info_panel(frame, frame_result, gallery.size, show_zones)

        cv2.imshow(window_name, frame)

        # FPS calculation
        if frame_count % 30 == 0:
            elapsed = time.time() - fps_start
            fps = frame_count / elapsed if elapsed > 0 else 0
            print(f"FPS: {fps:.1f} | Gallery: {gallery.size} | "
                  f"Visible: {frame_result['current_count']} | "
                  f"Unique: {frame_result['unique_count']}")

        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            break
        elif key == ord('r'):
            hen_counter.reset()
            print("Counter reset.")
        elif key == ord('z'):
            show_zones = not show_zones
            print(f"Zones: {'ON' if show_zones else 'OFF'}")

    cap.release()
    cv2.destroyAllWindows()

    elapsed = time.time() - fps_start
    fps = frame_count / elapsed if elapsed > 0 else 0
    print(f"\nProcessing complete: {frame_count} frames in {elapsed:.2f}s ({fps:.1f} FPS)")
    print(f"Total unique hens: {gallery.size}")


if __name__ == "__main__":
    run_main()
