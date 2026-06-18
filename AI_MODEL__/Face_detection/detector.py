"""
YOLOv8-seg Person Detection & Segmentation Module.

Detects persons in frames using YOLOv8 with instance segmentation,
extracts per-person binary masks and background-removed crops.

Architecture:
- YOLOv8x-seg pretrained on COCO (class 0 = "person")
- Instance segmentation masks from results.masks
- Background removal using per-person masks
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


@dataclass
class PersonDetection:
    """Single person detection with segmentation mask."""
    bbox: dict          # {"x1": float, "y1": float, "x2": float, "y2": float}
    confidence: float
    mask: np.ndarray    # Binary mask (H, W), dtype=bool
    cropped_image: np.ndarray  # Background-removed person crop (RGB)


class PersonDetector:
    """
    YOLOv8-seg based person detector.

    Detects persons (COCO class 0) with instance segmentation,
    produces background-removed crops for downstream face embedding.
    """

    PERSON_CLASS_ID = 0  # COCO "person"

    def __init__(
        self,
        model_path: str = "yolov8x-seg.pt",
        confidence: float = 0.5,
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
            raise ImportError("ultralytics is required. Install with: pip install ultralytics")

        self._model = YOLO(self._model_path)
        if self._device:
            self._model.to(self._device)
        self._loaded = True
        print(f"[PersonDetector] Loaded {self._model_path}")

    def detect(self, frame: np.ndarray) -> list[PersonDetection]:
        """
        Detect and segment persons in a frame.

        Args:
            frame: BGR image (H, W, 3) from OpenCV.

        Returns:
            List of PersonDetection objects, one per detected person.
        """
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

        for i, box in enumerate(results.boxes):
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            conf = float(box.conf[0])
            cls_id = int(box.cls[0])

            if cls_id != self.PERSON_CLASS_ID:
                continue

            bbox = {"x1": x1, "y1": y1, "x2": x2, "y2": y2}

            # Extract segmentation mask if available
            if has_masks and i < len(results.masks):
                mask_tensor = results.masks.data[i]
                mask = mask_tensor.cpu().numpy()
                # Resize mask to frame dimensions
                mask_resized = self._resize_mask(mask, frame.shape[:2])
                mask_binary = mask_resized > 0.5
            else:
                # Fallback: use bounding box as mask
                mask_binary = np.zeros(frame.shape[:2], dtype=bool)
                mask_binary[int(y1):int(y2), int(x1):int(x2)] = True

            # Create background-removed crop
            cropped = self._apply_mask(frame, mask_binary)

            detections.append(PersonDetection(
                bbox=bbox,
                confidence=conf,
                mask=mask_binary,
                cropped_image=cropped,
            ))

        return detections

    def _resize_mask(self, mask: np.ndarray, target_shape: tuple) -> np.ndarray:
        """Resize mask to target (H, W) using bilinear interpolation."""
        import cv2
        h, w = target_shape
        return cv2.resize(mask.astype(np.float32), (w, h), interpolation=cv2.INTER_LINEAR)

    def _apply_mask(self, frame: np.ndarray, mask: np.ndarray) -> np.ndarray:
        """Apply binary mask to frame, blacking out background."""
        masked = frame.copy()
        masked[~mask] = 0
        return masked

    def draw_detections(self, frame: np.ndarray, detections: list[PersonDetection]) -> np.ndarray:
        """Draw bounding boxes and masks on frame for visualization."""
        import cv2
        vis = frame.copy()

        for det in detections:
            b = det.bbox
            x1, y1, x2, y2 = int(b["x1"]), int(b["y1"]), int(b["x2"]), int(b["y2"])

            # Draw semi-transparent mask overlay
            overlay = vis.copy()
            overlay[det.mask] = [0, 255, 0]
            cv2.addWeighted(overlay, 0.25, vis, 0.75, 0, vis)

            # Draw bounding box
            cv2.rectangle(vis, (x1, y1), (x2, y2), (0, 255, 0), 2)

            # Draw confidence
            label = f"Person {det.confidence:.2f}"
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
            cv2.rectangle(vis, (x1, y1 - th - 8), (x1 + tw, y1), (0, 255, 0), -1)
            cv2.putText(vis, label, (x1, y1 - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)

        return vis
