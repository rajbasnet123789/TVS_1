"""
Hen Detection Pipeline (Channel Image Mode)

Per-channel hen detection, counting, and weight estimation using a single
YOLO detection model:
- Detection: AI_MODEL/best.pt (the only model used for detection)
- No ReID / no cross-camera identification — all chickens look identical, so
  re-identifying them across channels is meaningless. Detection-only.

"""

import cv2
import os
import sys
import time
import torch
import numpy as np
from ultralytics import YOLO

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "weight_model"))
from hen_counter import HenCounter
from weight_predictor import ChickenWeightPredictor

# ==========================================
# Configuration
# ==========================================
CONF_THRESHOLD = 0.35
MIN_BOX_AREA = 400
MAX_ASPECT_RATIO = 3.0

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WEIGHT_MODEL_DIR = os.path.join(SCRIPT_DIR, "weight_model")

# The single detection model used by this project (mounted at ./AI_MODEL).
CANONICAL_MODEL_PATH = os.path.normpath(
    os.path.join(SCRIPT_DIR, "..", "..", "AI_MODEL", "best.pt")
)

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
    """Load the single YOLO detection model (AI_MODEL/best.pt).

    Returns (model, device, weight_predictor, chicken_class_id).
    """
    if not os.path.exists(CANONICAL_MODEL_PATH):
        raise FileNotFoundError(
            f"Detection model not found: {CANONICAL_MODEL_PATH} "
            "(expected AI_MODEL/best.pt). No other model is used for detection."
        )
    print(f"YOLO model loaded: {CANONICAL_MODEL_PATH}")
    model = YOLO(CANONICAL_MODEL_PATH)

    device = "cuda" if torch.cuda.is_available() else "cpu"
    model.to(device)

    chicken_class_id, chicken_class_name, is_custom = detect_chicken_class_id(model)
    print(f"Target class: '{chicken_class_name}' (ID {chicken_class_id}) | Custom model: {is_custom}")

    weight_predictor = ChickenWeightPredictor(
        model_path=os.path.join(WEIGHT_MODEL_DIR, "weight_model.ubj"),
        stats_path=os.path.join(WEIGHT_MODEL_DIR, "norm_stats.json"),
    )

    return model, device, weight_predictor, chicken_class_id


def point_in_roi(cx, cy, roi_polygon, frame_w, frame_h):
    """Check if point (cx, cy) is inside the ROI polygon (normalized coords)."""
    pts = np.array(roi_polygon, dtype=np.float32)
    pts[:, 0] *= frame_w
    pts[:, 1] *= frame_h
    return cv2.pointPolygonTest(pts, (cx, cy), False) >= 0


def detect_single_image(model, device, weight_predictor, image_path, chicken_class_id, roi_polygon=None):
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

            detections.append({
                "bbox": {"x": x1, "y": y1, "w": bw, "h": bh},
                "confidence": conf,
                "class_id": cls_id,
                "class_name": results.names.get(cls_id, str(cls_id)),
                "weight": weight,
            })

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

    model, device, weight_predictor, chicken_class_id = load_all_models()

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
                model, device, weight_predictor, img_path, chicken_class_id, roi_polygon=roi
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
