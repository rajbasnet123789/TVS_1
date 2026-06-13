import asyncio
import logging
import os
import numpy as np

from app.config import settings

logger = logging.getLogger(__name__)


class YOLODetector:
    def __init__(self, model_name: str = "yolov8x.pt"):
        _root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
        candidates = [
            os.path.join(_root, "AI_MODEL", model_name),
            f"/app/AI_MODEL/{model_name}",
            model_name,
            "yolov8x.pt",
        ]
        for c in candidates:
            if os.path.exists(c):
                model_name = c
                break
        self.model_name = model_name
        self._model = None
        self._sahi_model = None

    async def load(self):
        if self._model is not None:
            return
        logger.info(f"Loading YOLO model: {self.model_name}")
        from ultralytics import YOLO
        loop = asyncio.get_running_loop()
        self._model = await loop.run_in_executor(
            None, lambda: YOLO(self.model_name)
        )
        logger.info(f"YOLO model loaded: {self.model_name}")

    def _load_sahi(self):
        if self._sahi_model is not None:
            return
        try:
            from sahi import AutoDetectionModel
            self._sahi_model = AutoDetectionModel.from_pretrained(
                model_type="ultralytics",
                model_path=self.model_name,
                confidence_threshold=0.4,
                device="cuda:0" if __import__("torch").cuda.is_available() else "cpu",
            )
            logger.info("SAHI detection model loaded")
        except Exception as e:
            logger.warning(f"SAHI load failed: {e}")

    def _sahi_detect(self, frame: np.ndarray, conf_threshold: float) -> list[dict]:
        from sahi.predict import get_sliced_prediction

        h, w = frame.shape[:2]
        slice_h = min(640, h)
        slice_w = min(640, w)
        overlap_h = 0.2
        overlap_w = 0.2

        result = get_sliced_prediction(
            frame,
            self._sahi_model,
            slice_height=slice_h,
            slice_width=slice_w,
            overlap_height_ratio=overlap_h,
            overlap_width_ratio=overlap_w,
            postprocess_type="NMS",
            postprocess_match_threshold=0.5,
            verbose=0,
        )

        detections = []
        for pred in result.object_prediction_list:
            if pred.category.id != 14:
                continue
            if pred.score.value < conf_threshold:
                continue
            bbox = pred.bbox
            detections.append({
                "bbox": {
                    "x": float(bbox.minx),
                    "y": float(bbox.miny),
                    "w": float(bbox.maxx - bbox.minx),
                    "h": float(bbox.maxy - bbox.miny),
                },
                "confidence": float(pred.score.value),
                "class_id": 14,
                "class_name": "bird",
            })
        return detections

    async def detect(
        self, frame: np.ndarray,         conf_threshold: float = 0.4
    ) -> list[dict]:
        if self._model is None:
            await self.load()

        h, w = frame.shape[:2]

        loop = asyncio.get_running_loop()
        results = await loop.run_in_executor(
            None,
            lambda: self._model(
                frame,
                conf=conf_threshold,
                imgsz=1280,
                classes=[14],
                verbose=False,
            )
        )

        detections = []
        if len(results) == 0:
            return detections

        boxes = results[0].boxes
        if boxes is None:
            return detections

        for box in boxes:
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            conf = float(box.conf[0])
            cls_id = int(box.cls[0])
            cls_name = self._model.names[cls_id] if self._model.names else str(cls_id)

            detections.append({
                "bbox": {"x": x1, "y": y1, "w": x2 - x1, "h": y2 - y1},
                "confidence": conf,
                "class_id": cls_id,
                "class_name": cls_name,
            })

        return detections

    def unload(self):
        self._model = None
        self._sahi_model = None
        logger.info("YOLO model unloaded")


detector = YOLODetector()
