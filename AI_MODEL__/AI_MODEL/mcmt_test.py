import cv2
import os
import sys
import time
import torch
import numpy as np
from dataclasses import dataclass, field
from typing import Optional

from ultralytics import YOLO

sys.path.insert(0, os.path.dirname(__file__))

# ==========================================
# MCMT Configuration
# ==========================================
VIDEO_PATH = r"D:\WhatsApp Video 2026-06-13 at 9.27.30 AM.mp4"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# The single detection model used by this project (mounted at ./AI_MODEL).
MODEL_PATH = os.path.normpath(os.path.join(SCRIPT_DIR, "..", "..", "AI_MODEL", "best.pt"))
TRACKER_CONFIG = os.path.join(SCRIPT_DIR, "botsort_custom.yaml")
CONF_THRESHOLD = 0.4
CLASSES = [14]  # COCO bird class
MATCH_THRESHOLD = 0.5

# Camera simulation: 3 views from same video
CAMERAS = {
    "cam_north": {
        "name": "North Wing Camera",
        "crop": None,  # full frame
        "color_shift": 0,
    },
    "cam_south": {
        "name": "South Wing Camera",
        "crop": (0.3, 0.0, 1.0, 1.0),  # right 70% of frame
        "color_shift": 10,
    },
    "cam_east": {
        "name": "East Wing Camera",
        "crop": (0.0, 0.0, 0.7, 1.0),  # left 70% of frame
        "color_shift": -10,
    },
}


MIEWID_REPO = "conservationxlabs/miewid-msv3"
MIEWID_DIM = 2152


# ==========================================
# Embedding Extractor (MiewID via direct load)
# ==========================================
class EmbeddingExtractor:
    def __init__(self):
        self._backbone = None
        self._bn = None
        self._transform = None
        self._device = "cpu"
        self._backbone_name = None

    def load(self):
        self._device = "cuda:0" if torch.cuda.is_available() else "cpu"

        try:
            self._load_miewid()
            self._backbone_name = "miewid"
            print(f"[ReID] MiewID loaded on {self._device} (dim={MIEWID_DIM})")
            return
        except Exception as e:
            print(f"[ReID] MiewID load failed: {e}")

        try:
            from boxmot.reid.core import ReID
            reid = ReID(device=self._device)
            self._backbone = reid.model
            self._bn = None
            self._backbone_name = "osnet"
            print(f"[ReID] OSNet fallback loaded on {self._device}")
        except Exception as e:
            print(f"[ReID] No ReID model available: {e}")

    def _load_miewid(self):
        import torch
        import timm
        import torch.nn as nn
        import torch.nn.functional as F
        from safetensors.torch import load_file
        from huggingface_hub import hf_hub_download

        class GeM(nn.Module):
            def __init__(self, p=3, eps=1e-6):
                super().__init__()
                self.p = nn.Parameter(torch.ones(1) * p)
                self.eps = eps
            def forward(self, x):
                return F.avg_pool2d(x.clamp(min=self.eps).pow(self.p), (x.size(-2), x.size(-1))).pow(1. / self.p)

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

        from timm.data import resolve_data_config, create_transform
        data_config = resolve_data_config(self._backbone.pretrained_cfg)
        self._transform = create_transform(**data_config, is_training=False)

    def _preprocess_miewid(self, crop: np.ndarray) -> Optional[torch.Tensor]:
        from PIL import Image
        if crop.shape[0] == 0 or crop.shape[1] == 0:
            return None
        pil = Image.fromarray(crop[:, :, ::-1] if crop.shape[2] == 3 else crop)
        return self._transform(pil).unsqueeze(0)

    def _preprocess_osnet(self, crop: np.ndarray) -> torch.Tensor:
        import cv2
        resized = cv2.resize(crop, (64, 128), interpolation=cv2.INTER_LINEAR)
        pre = self._backbone.inference_preprocess(resized)
        t = torch.from_numpy(pre).float()
        if t.ndim == 3:
            t = t.permute(2, 0, 1).unsqueeze(0)
        return t.to(self._backbone.device)

    def extract(self, frame: np.ndarray, bboxes: list[dict]) -> list[Optional[np.ndarray]]:
        if self._backbone_name is None:
            return [None] * len(bboxes)

        crops = []
        valid_indices = []
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
            if self._backbone_name == "miewid":
                t = self._preprocess_miewid(crop)
            else:
                t = self._preprocess_osnet(crop)
            if t is None:
                continue
            crops.append(t)
            valid_indices.append(i)

        if not crops:
            return [None] * len(bboxes)

        try:
            batch = torch.cat(crops, dim=0).to(self._device)
            with torch.no_grad():
                if self._backbone_name == "miewid":
                    feat = self._backbone(batch)
                    feat = feat.view(feat.size(0), -1)
                    features = self._bn(feat)
                else:
                    features = self._backbone.model(batch)
            features = features.cpu().numpy()

            result = [None] * len(bboxes)
            for j, idx in enumerate(valid_indices):
                if j < len(features):
                    emb = features[j].flatten()
                    norm = np.linalg.norm(emb)
                    if norm > 0:
                        emb = emb / norm
                    result[idx] = emb
            return result
        except Exception as e:
            print(f"[ReID] Extraction failed: {e}")
            return [None] * len(bboxes)


# ==========================================
# FAISS Embedding Gallery
# ==========================================
class EmbeddingGallery:
    def __init__(self, dim: int = 2152, threshold: float = MATCH_THRESHOLD):
        self.dim = dim
        self.threshold = threshold
        self._embeddings: dict[int, np.ndarray] = {}
        self._metadata: dict[int, dict] = {}
        self._next_id = 1
        try:
            import faiss
            self._index = faiss.IndexFlatIP(dim)
            self._id_map: list[int] = []
            self._use_faiss = True
            print("[Gallery] FAISS IndexFlatIP initialized")
        except ImportError:
            self._index = None
            self._id_map = []
            self._use_faiss = False
            print("[Gallery] Using brute-force cosine similarity (faiss not available)")

    def add(self, embedding: np.ndarray, camera_id: str, confidence: float = 0.0) -> int:
        gid = self._next_id
        self._next_id += 1
        self._embeddings[gid] = embedding.copy()
        self._metadata[gid] = {
            "camera_id": camera_id,
            "confidence": confidence,
            "first_seen": time.time(),
            "last_seen": time.time(),
            "detection_count": 1,
        }
        if self._use_faiss:
            self._index.add(embedding.reshape(1, -1).astype(np.float32))
            self._id_map.append(gid)
        else:
            self._id_map.append(gid)
        return gid

    def search(self, query: np.ndarray, k: int = 5, threshold: float = 0.5) -> list[tuple[int, float]]:
        if not self._id_map:
            return []

        if self._use_faiss and self._index.ntotal > 0:
            k = min(k, self._index.ntotal)
            q = query.reshape(1, -1).astype(np.float32)
            dists, idxs = self._index.search(q, k)
            results = []
            for dist, idx in zip(dists[0], idxs[0]):
                if 0 <= idx < len(self._id_map):
                    gid = self._id_map[idx]
                    if dist >= threshold:
                        results.append((gid, float(dist)))
            return results
        else:
            ids = list(self._embeddings.keys())
            matrix = np.stack([self._embeddings[g] for g in ids]).astype(np.float32)
            norms = np.linalg.norm(matrix, axis=1, keepdims=True)
            norms = np.where(norms == 0, 1, norms)
            matrix_n = matrix / norms
            q_norm = np.linalg.norm(query)
            if q_norm == 0:
                return []
            q_n = query.astype(np.float32).reshape(1, -1) / q_norm
            scores = (matrix_n @ q_n.T).flatten()
            top_k = np.argsort(scores)[::-1][:k]
            return [(ids[i], float(scores[i])) for i in top_k if scores[i] >= threshold]

    def update(self, gid: int, embedding: np.ndarray, camera_id: str, confidence: float = 0.0):
        if gid not in self._embeddings:
            return
        old = self._embeddings[gid]
        alpha = 0.3
        updated = alpha * embedding + (1 - alpha) * old
        norm = np.linalg.norm(updated)
        if norm > 0:
            updated = updated / norm
        self._embeddings[gid] = updated
        self._metadata[gid]["last_seen"] = time.time()
        self._metadata[gid]["camera_id"] = camera_id
        self._metadata[gid]["detection_count"] += 1
        if confidence > 0:
            c = self._metadata[gid]["detection_count"]
            old_conf = self._metadata[gid]["confidence"]
            self._metadata[gid]["confidence"] = (old_conf * (c - 1) + confidence) / c

    def match_or_create(self, embedding: np.ndarray, camera_id: str, confidence: float = 0.0) -> int:
        """Match against this gallery (single stream), else create a new identity."""
        matches = self.search(embedding, k=5, threshold=self.threshold)
        best_gid = None
        best_score = 0.0
        for gid, score in matches:
            if score > best_score:
                best_score = score
                best_gid = gid
        if best_gid is not None:
            self.update(best_gid, embedding, camera_id, confidence)
            return best_gid
        return self.add(embedding, camera_id, confidence)

    def get_metadata(self, gid: int) -> Optional[dict]:
        return self._metadata.get(gid)

    def size(self) -> int:
        return len(self._embeddings)

    def get_active(self, max_age: float = 60.0) -> list[int]:
        now = time.time()
        return [g for g, m in self._metadata.items() if now - m["last_seen"] < max_age]


# ==========================================
# Per-Stream Tracker (single-stream ReID only)
# ==========================================
class SingleStreamTracker:
    """Tracks identities within each camera stream only.

    All chickens look identical, so matching embeddings across different
    cameras is meaningless. ReID is therefore applied per camera (single
    stream) — an identity is only ever matched against detections from the
    SAME camera, never re-identified across cameras.
    """

    def __init__(self):
        self.extractor = EmbeddingExtractor()
        self._galleries: dict[str, EmbeddingGallery] = {}
        self._match_threshold = MATCH_THRESHOLD

    def load(self):
        self.extractor.load()
        print(f"[Tracker] Per-stream ReID (no cross-camera matching)")

    def process_frame(self, detections: list[dict], track_ids: list[Optional[int]],
                      frame: np.ndarray, camera_id: str) -> list[dict]:
        if not detections:
            return []

        bboxes = [d["bbox"] for d in detections]
        embeddings = self.extractor.extract(frame, bboxes)

        gallery = self._galleries.get(camera_id)
        if gallery is None:
            gallery = EmbeddingGallery(dim=MIEWID_DIM)
            self._galleries[camera_id] = gallery

        results = []
        for det, tid, emb in zip(detections, track_ids, embeddings):
            entry = {**det}
            if emb is None or tid is None:
                entry["global_id"] = None
                results.append(entry)
                continue

            # ReID against THIS camera's gallery only.
            gid = gallery.match_or_create(emb, camera_id, det.get("confidence", 0.0))
            entry["global_id"] = gid
            results.append(entry)

        return results

    def gallery(self, camera_id: str) -> EmbeddingGallery:
        return self._galleries.setdefault(camera_id, EmbeddingGallery(dim=MIEWID_DIM))

    def gallery_sizes(self) -> dict[str, int]:
        return {cid: g.size() for cid, g in self._galleries.items()}


# ==========================================
# Camera Simulation
# ==========================================
class SimulatedCamera:
    def __init__(self, cam_id: str, cfg: dict, cap: cv2.VideoCapture):
        self.cam_id = cam_id
        self.cfg = cfg
        self.cap = cap
        self.frame_idx = 0

    def read_frame(self) -> Optional[np.ndarray]:
        ret, frame = self.cap.read()
        if not ret:
            return None

        self.frame_idx += 1
        h, w = frame.shape[:2]

        crop = self.cfg.get("crop")
        if crop:
            x1 = int(crop[0] * w)
            y1 = int(crop[1] * h)
            x2 = int(crop[2] * w)
            y2 = int(crop[3] * h)
            frame = frame[y1:y2, x1:x2]

        shift = self.cfg.get("color_shift", 0)
        if shift != 0:
            frame = frame.astype(np.int16)
            frame = np.clip(frame + shift, 0, 255).astype(np.uint8)

        return frame


# ==========================================
# Visualization
# ==========================================
COLORS = [
    (0, 255, 0), (255, 0, 0), (0, 0, 255), (255, 255, 0),
    (0, 255, 255), (255, 0, 255), (128, 255, 0), (255, 128, 0),
    (0, 128, 255), (255, 255, 128), (128, 0, 255), (255, 128, 128),
]


def draw_detections(frame, detections, cam_name):
    for det in detections:
        bbox = det["bbox"]
        x1, y1 = int(bbox["x"]), int(bbox["y"])
        x2, y2 = int(bbox["x"] + bbox["w"]), int(bbox["y"] + bbox["h"])

        gid = det.get("global_id")
        tid = det.get("track_id")
        color = COLORS[gid % len(COLORS)] if gid else (128, 128, 128)

        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

        label_parts = []
        if gid is not None:
            label_parts.append(f"G{gid}")
        if tid is not None:
            label_parts.append(f"T{tid}")
        label = " ".join(label_parts)

        if label:
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
            cv2.rectangle(frame, (x1, y1 - th - 8), (x1 + tw + 4, y1), color, -1)
            cv2.putText(frame, label, (x1 + 2, y1 - 4),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)

    h, w = frame.shape[:2]
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, 0), (w, 30), (0, 0, 0), -1)
    cv2.addWeighted(overlay, 0.6, frame, 0.4, 0, frame)
    cv2.putText(frame, cam_name, (10, 22),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)


def draw_global_panel(frame, tracker, cam_ids):
    h, w = frame.shape[:2]
    panel_w = 320
    panel_h = 120 + len(cam_ids) * 20
    overlay = frame.copy()
    cv2.rectangle(overlay, (w - panel_w - 10, 10), (w - 10, panel_h), (0, 0, 0), -1)
    cv2.addWeighted(overlay, 0.6, frame, 0.4, 0, frame)

    x0 = w - panel_w - 5
    y0 = 35
    lh = 22

    cv2.putText(frame, "Per-Stream ReID (no cross-camera)", (x0, y0),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 2)
    y0 += lh

    for cam_id in cam_ids:
        size = tracker.gallery(cam_id).size()
        cv2.putText(frame, f"{cam_id}: {size} identities", (x0, y0),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (180, 180, 180), 1)
        y0 += lh - 4


# ==========================================
# MAIN
# ==========================================
def main():
    print("=" * 60)
    print("  Multi-Camera Hen Tracking Test")
    print("  best.pt + BoT-SORT + per-stream ReID (no cross-camera matching)")
    print("=" * 60)
    print()

    if not os.path.exists(VIDEO_PATH):
        print(f"Error: Video not found: {VIDEO_PATH}")
        return

    model = YOLO(MODEL_PATH)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model.to(device)
    print(f"[Model] YOLOv8m on {device}")

    tracker = SingleStreamTracker()
    tracker.load()
    print()

    cameras = {}
    for cam_id, cam_cfg in CAMERAS.items():
        cap = cv2.VideoCapture(VIDEO_PATH)
        cameras[cam_id] = SimulatedCamera(cam_id, cam_cfg, cap)
        print(f"[Camera] {cam_cfg['name']} ({cam_id})")

    print()
    print("=" * 60)
    print("  Processing...")
    print("=" * 60)
    print()

    window_name = "MCMT - Multi-Camera Hen Tracking"
    cv2.namedWindow(window_name, cv2.WINDOW_AUTOSIZE)

    frame_num = 0
    total_detections = 0
    per_cam_stats = {cid: {"frames": 0, "dets": 0, "ids": set()} for cid in CAMERAS}
    all_global_ids = set()
    start_time = time.time()

    while True:
        frames = {}
        for cam_id, cam in cameras.items():
            f = cam.read_frame()
            if f is not None:
                frames[cam_id] = f

        if not frames:
            break

        frame_num += 1
        frame_dets = []

        for cam_id, frame in frames.items():
            results = model.track(
                source=frame, conf=CONF_THRESHOLD, classes=CLASSES,
                imgsz=1280, device=device, verbose=False, tracker=TRACKER_CONFIG, persist=True,
            )[0]

            dets = []
            tids = []
            if results.boxes is not None and len(results.boxes) > 0:
                for box in results.boxes:
                    x1, y1, x2, y2 = box.xyxy[0].tolist()
                    dets.append({
                        "bbox": {"x": x1, "y": y1, "w": x2 - x1, "h": y2 - y1},
                        "confidence": float(box.conf[0]),
                        "class_id": int(box.cls[0]),
                        "class_name": results.names.get(int(box.cls[0]), "hen"),
                    })
                    tids.append(int(box.id[0]) if box.id is not None else None)

            tracked = tracker.process_frame(dets, tids, frame, cam_id)

            cam_name = CAMERAS[cam_id]["name"]
            draw_detections(frame, tracked, cam_name)
            draw_global_panel(frame, tracker, list(CAMERAS.keys()))

            per_cam_stats[cam_id]["frames"] += 1
            per_cam_stats[cam_id]["dets"] += len(tracked)
            for d in tracked:
                if d.get("global_id"):
                    gid = d["global_id"]
                    per_cam_stats[cam_id]["ids"].add(gid)
                    all_global_ids.add(gid)

            frame_dets.append((cam_id, len(tracked), [d.get("global_id") for d in tracked]))

        h, w = list(frames.values())[0].shape[:2]
        combined = np.zeros((h, w * len(frames) + 10 * (len(frames) - 1), 3), dtype=np.uint8)
        for i, (cam_id, frame) in enumerate(frames.items()):
            x_off = i * (w + 10)
            combined[:frame.shape[0], x_off:x_off + frame.shape[1]] = frame

        cv2.imshow(window_name, combined)

        det_str = " | ".join([f"{cid}:{n}hens GIDs={gids}" for cid, n, gids in frame_dets])
        print(f"Frame {frame_num:3d}: {det_str}")

        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            break

    elapsed = time.time() - start_time

    for cam in cameras.values():
        cam.cap.release()
    cv2.destroyAllWindows()

    print()
    print("=" * 60)
    print("  RESULTS SUMMARY")
    print("=" * 60)
    print()
    print(f"  Frames processed:     {frame_num}")
    print(f"  Elapsed time:         {elapsed:.2f}s")
    print(f"  Processing FPS:       {frame_num / elapsed:.1f}")
    print("  ReID mode:            per-stream only (no cross-camera matching)")
    print()
    print("  Per-Camera Statistics:")
    for cam_id, stats in per_cam_stats.items():
        name = CAMERAS[cam_id]["name"]
        ids_list = sorted(stats["ids"])
        print(f"    {name}:")
        print(f"      Frames: {stats['frames']}, Detections: {stats['dets']}")
        print(f"      Local IDs seen: {ids_list}")
    print()
    print(f"  All Local IDs:        {sorted(all_global_ids)}")
    print(f"  Total unique hens:    {len(all_global_ids)}")
    print()

    print("  Gallery Contents (per camera):")
    for cam_id in CAMERAS:
        gallery = tracker.gallery(cam_id)
        print(f"    Camera {cam_id} ({gallery.size()} identities):")
        for gid in sorted(gallery.get_active(max_age=999)):
            meta = gallery.get_metadata(gid)
            if meta:
                print(f"      G{gid:3d}: conf={meta['confidence']:.3f} "
                      f"detections={meta['detection_count']}")
    print()
    print("=" * 60)


if __name__ == "__main__":
    main()
