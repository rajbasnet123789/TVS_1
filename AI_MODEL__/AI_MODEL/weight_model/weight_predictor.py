"""
Chicken Weight Estimation — Complete Integration Package.

Two usage modes:

1. Your own detector — just provide binary masks:
    from weight_predictor import ChickenWeightPredictor
    p = ChickenWeightPredictor()
    weight_kg = p.predict(mask_bin)  # HxW uint8 mask, 0 or 255

2. End-to-end with YOLO detection (pre-trained chicken model included):
    from weight_predictor import ChickenWeightPredictor
    p = ChickenWeightPredictor()
    results = p.detect_and_predict(frame)  # returns [(id, weight, bbox), ...]
"""
import json, csv
import cv2
import numpy as np
import xgboost as xgb
from pathlib import Path

FEATURE_NAMES = [
    "area", "perimeter", "rmin", "rmax",
    "convex_area", "rect_area",
    "solidity", "extent", "circularity",
    "aspect_ratio", "equiv_diameter",
]

MODEL_DIR = Path(__file__).parent


def extract_features(mask_bin, min_area=50):
    if mask_bin is None or cv2.countNonZero(mask_bin) == 0:
        return None
    contours, _ = cv2.findContours(mask_bin, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    cnt = max(contours, key=cv2.contourArea)
    area = cv2.contourArea(cnt)
    if area < min_area:
        return None
    perimeter = cv2.arcLength(cnt, True)
    if len(cnt) >= 5:
        (cx, cy), (rmin, rmax), angle = cv2.fitEllipse(cnt)
    else:
        rmin = rmax = 0.0
    hull = cv2.convexHull(cnt)
    convex_area = cv2.contourArea(hull)
    _, _, w, h = cv2.boundingRect(cnt)
    rect_area = float(w * h)
    solidity = area / convex_area if convex_area > 0 else 0.0
    extent = area / rect_area if rect_area > 0 else 0.0
    circularity = (4 * np.pi * area) / (perimeter * perimeter) if perimeter > 0 else 0.0
    aspect_ratio = (rmax / rmin) if rmin > 0 else 1.0
    equiv_diameter = np.sqrt(4 * area / np.pi)
    return np.array([
        area, perimeter, rmin, rmax,
        convex_area, rect_area,
        solidity, extent, circularity,
        aspect_ratio, equiv_diameter,
    ], dtype=np.float32)


class ChickenWeightPredictor:
    """Predict chicken weight from a binary mask or end-to-end with YOLO."""

    def __init__(self, model_path=None, stats_path=None, yolo_path=None):
        model_path = model_path or str(MODEL_DIR / "weight_model.ubj")
        stats_path = stats_path or str(MODEL_DIR / "norm_stats.json")
        yolo_path = yolo_path or str(MODEL_DIR / "yolo_chicken" / "best.pt")

        with open(stats_path) as f:
            stats = json.load(f)
        self.feat_min = np.array(stats["min"])
        self.feat_max = np.array(stats["max"])
        self.model = xgb.XGBRegressor()
        self.model.load_model(model_path)

        self.yolo = None
        if Path(yolo_path).exists():
            from ultralytics import YOLO
            self.yolo = YOLO(yolo_path)
            self._yolo_loaded = True
        else:
            self._yolo_loaded = False

    def predict(self, mask_bin):
        """Predict weight from binary mask (HxW uint8). Returns Kg or None."""
        feats = extract_features(mask_bin)
        if feats is None:
            return None
        feats_norm = (feats - self.feat_min) / (self.feat_max - self.feat_min + 1e-8)
        return float(self.model.predict(feats_norm.reshape(1, -1))[0])

    def detect_and_predict(self, image_bgr, conf=0.35, iou=0.5, roi_polygon=None):
        """
        End-to-end: YOLO detection + weight prediction.
        
        Args:
            image_bgr: OpenCV BGR image
            conf: YOLO confidence threshold
            iou: YOLO IoU threshold
            roi_polygon: optional [[x1,y1],...] normalized 0-1 coords
        
        Returns:
            List of (chicken_id, weight_kg, [x1,y1,x2,y2])
        """
        if not self._yolo_loaded:
            raise RuntimeError("YOLO model not found at yolo_chicken/best.pt")
        
        h, w = image_bgr.shape[:2]
        results = self.yolo(image_bgr, conf=conf, iou=iou, verbose=False)[0]
        
        chickens = []
        cid = 0
        for box in results.boxes:
            x1, y1, x2, y2 = [int(v) for v in box.xyxy[0].tolist()]
            cx, cy = (x1 + x2) / 2, (y1 + y2) / 2

            if roi_polygon:
                pts = np.array(roi_polygon, dtype=np.float32)
                pts[:, 0] *= w
                pts[:, 1] *= h
                if cv2.pointPolygonTest(pts, (cx, cy), False) < 0:
                    continue

            bw, bh = x2 - x1, y2 - y1
            box_area = bw * bh
            if box_area < 400:
                continue
            aspect = max(bw, bh) / max(min(bw, bh), 1)
            if aspect > 3.0:
                continue

            mask = np.zeros((h, w), dtype=np.uint8)
            cv2.rectangle(mask, (x1, y1), (x2, y2), 255, -1)
            weight = self.predict(mask)
            if weight is not None:
                cid += 1
                chickens.append((cid, weight, [x1, y1, x2, y2]))
        return chickens


if __name__ == "__main__":
    import sys

    p = ChickenWeightPredictor()

    if len(sys.argv) >= 2 and sys.argv[1] == "--yolo":
        # End-to-end mode
        img = cv2.imread(sys.argv[2])
        if img is None:
            print(f"Could not read {sys.argv[2]}")
            sys.exit(1)
        # Optional ROI: cols 0-8, rows 5-9 (bottom area)
        roi = [[0.0, 0.5], [0.9, 0.5], [0.9, 1.0], [0.0, 1.0]]
        chickens = p.detect_and_predict(img, roi_polygon=roi)
        print(f"Detected {len(chickens)} chickens:")
        for cid, wgt, bbox in chickens:
            print(f"  #{cid}: {wgt:.3f} Kg  box={bbox}")

        # Save CSV
        out_csv = Path("output") / f"{Path(sys.argv[2]).stem}_weights.csv"
        out_csv.parent.mkdir(exist_ok=True)
        with open(out_csv, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["Chicken ID", "Weight (Kg)"])
            for cid, wgt, _ in chickens:
                writer.writerow([cid, round(wgt, 3)])
        print(f"Saved to {out_csv}")

    elif len(sys.argv) >= 2:
        # Legacy: predict from mask image
        mask = cv2.imread(sys.argv[1], cv2.IMREAD_GRAYSCALE)
        _, mask = cv2.threshold(mask, 127, 255, cv2.THRESH_BINARY)
        weight = p.predict(mask)
        if weight:
            print(f"Predicted weight: {weight:.3f} Kg")
        else:
            print("No valid chicken mask detected")
    else:
        print("Usage:")
        print("  python weight_predictor.py --yolo <image>   End-to-end YOLO + weight")
        print("  python weight_predictor.py <mask.png>       Weight from binary mask")
