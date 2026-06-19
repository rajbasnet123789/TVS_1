"""
YOLOv8-seg Person Detection & Segmentation.

Detects persons (COCO class 0) with instance segmentation.
Handles both near and far persons with adaptive thresholds.
"""

import os
import numpy as np
from dataclasses import dataclass
from typing import Optional

try:
    from ultralytics import YOLO
    HAS_YOLO = True
except ImportError:
    HAS_YOLO = False

import cv2


@dataclass
class PersonDetection:
    """Single person detection with segmentation mask."""
    bbox: dict          # {"x1": float, "y1": float, "x2": float, "y2": float}
    confidence: float
    mask: np.ndarray    # Binary mask (H, W), dtype=bool
    cropped_image: np.ndarray  # Background-removed person crop (RGB)
    face_region: np.ndarray    # Extracted upper body for face detection


class PersonDetector:
    """
    YOLOv8-seg based person detector.

    Detects persons (COCO class 0) with instance segmentation.
    Produces face-ready crops for downstream face embedding.
    """

    PERSON_CLASS_ID = 0  # COCO "person"

    def __init__(
        self,
        model_path: str = "yolov8n-seg.pt",
        confidence: float = 0.3,
        imgsz: int = 640,
        device: str = None,
    ):
        self._model = None
        self._model_path = model_path
        self._confidence = confidence
        self._imgsz = imgsz
        self._device = device
        self._loaded = False

    def load(self):
        """Load the YOLOv8-seg model."""
        if not HAS_YOLO:
            raise ImportError("ultralytics required: pip install ultralytics")
        self._model = YOLO(self._model_path)
        if self._device:
            self._model.to(self._device)
        self._loaded = True
        print(f"[PersonDetector] Loaded {self._model_path}")

    def detect(self, frame: np.ndarray) -> list:
        """Detect and segment persons in a frame."""
        if not self._loaded:
            raise RuntimeError("Model not loaded. Call load() first.")

        results = self._model(
            source=frame,
            conf=self._confidence,
            imgsz=self._imgsz,
            verbose=False,
            classes=[self.PERSON_CLASS_ID],
        )[0]

        detections = []
        if results.boxes is None or len(results.boxes) == 0:
            return detections

        has_masks = results.masks is not None and len(results.masks) > 0
        h, w = frame.shape[:2]

        for i, box in enumerate(results.boxes):
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            conf = float(box.conf[0])
            cls_id = int(box.cls[0])

            if cls_id != self.PERSON_CLASS_ID:
                continue

            # Clamp to frame
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(w, x2), min(h, y2)
            bbox = {"x1": x1, "y1": y1, "x2": x2, "y2": y2}

            # Extract segmentation mask
            if has_masks and i < len(results.masks):
                mask = results.masks.data[i].cpu().numpy()
                mask_resized = cv2.resize(mask.astype(np.float32), (w, h),
                                          interpolation=cv2.INTER_LINEAR)
                mask_binary = mask_resized > 0.5
            else:
                mask_binary = np.zeros((h, w), dtype=bool)
                mask_binary[int(y1):int(y2), int(x1):int(x2)] = True

            # Background-removed crop
            masked = frame.copy()
            masked[~mask_binary] = 0

            # Extract face region (upper 45%)
            face_region = self._extract_face_region(frame, bbox)

            detections.append(PersonDetection(
                bbox=bbox,
                confidence=conf,
                mask=mask_binary,
                cropped_image=masked,
                face_region=face_region,
            ))

        return detections

    def _extract_face_region(self, frame: np.ndarray, bbox: dict) -> np.ndarray:
        """Extract upper body (head + shoulders) from person bbox."""
        x1 = max(0, int(bbox["x1"]))
        y1 = max(0, int(bbox["y1"]))
        x2 = min(frame.shape[1], int(bbox["x2"]))
        y2 = min(frame.shape[0], int(bbox["y2"]))

        h = y2 - y1
        w = x2 - x1

        # Top 45% of person (head + shoulders)
        face_y2 = y1 + int(h * 0.45)
        face_y1 = max(0, y1 - int(h * 0.05))

        # Add horizontal padding
        pad = int(w * 0.15)
        fx1 = max(0, x1 - pad)
        fx2 = min(frame.shape[1], x2 + pad)

        face_crop = frame[face_y1:face_y2, fx1:fx2]
        if face_crop.size == 0:
            return frame[y1:y2, x1:x2]
        return face_crop

    def draw_detections(self, frame: np.ndarray, detections: list) -> np.ndarray:
        """Draw bounding boxes and masks on frame."""
        vis = frame.copy()

        for det in detections:
            b = det.bbox
            x1, y1 = int(b["x1"]), int(b["y1"])
            x2, y2 = int(b["x2"]), int(b["y2"])

            # Semi-transparent mask
            overlay = vis.copy()
            overlay[det.mask] = [0, 255, 0]
            cv2.addWeighted(overlay, 0.25, vis, 0.75, 0, vis)

            # Bounding box
            cv2.rectangle(vis, (x1, y1), (x2, y2), (0, 255, 0), 2)

            # Label
            label = f"Person {det.confidence:.2f}"
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
            cv2.rectangle(vis, (x1, y1 - th - 8), (x1 + tw, y1), (0, 255, 0), -1)
            cv2.putText(vis, label, (x1, y1 - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)

        return vis
