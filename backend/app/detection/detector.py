import asyncio
import hashlib
import logging
import os

import numpy as np

from app.config import settings

logger = logging.getLogger(__name__)


class HealthClassifier:
    def __init__(self):
        self._health_model = None

    async def load_health(self):
        if self._health_model is not None:
            return
        model_name = settings.model_health_path or "best.pt"
        _root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
        candidates = [
            model_name,
            os.path.join(_root, "AI_MODEL__", "AI_MODEL", model_name),
            os.path.join(_root, "AI_MODEL", model_name),
            f"/app/{model_name}",
            f"/app/AI_MODEL/{model_name}",
            "best.pt",
        ]
        found = model_name
        for c in candidates:
            if os.path.exists(c):
                found = c
                break
        if settings.model_health_checksum_sha256:
            try:
                with open(found, "rb") as f:
                    actual = hashlib.sha256(f.read()).hexdigest()
            except Exception as e:
                raise ValueError(f"Failed to read health model file for checksum verification: {e}")

            if actual != settings.model_health_checksum_sha256:
                raise ValueError(
                    f"Health model SHA-256 mismatch: expected={settings.model_health_checksum_sha256}, actual={actual}"
                )
            else:
                logger.info("Health model SHA-256 checksum verified")

        logger.info(f"Loading health model: {found}")
        from ultralytics import YOLO
        loop = asyncio.get_running_loop()
        self._health_model = await loop.run_in_executor(
            None, lambda: YOLO(found)
        )
        logger.info(f"Health model loaded: {found}")

    async def classify(
        self, frame: np.ndarray, detections: list[dict], conf_threshold: float = 0.25
    ) -> list[dict]:
        if self._health_model is None:
            await self.load_health()
        if not detections:
            return []

        import cv2
        loop = asyncio.get_running_loop()
        results = []
        for d in detections:
            bbox = d["bbox"]
            x1, y1, w, h = int(bbox["x"]), int(bbox["y"]), int(bbox["w"]), int(bbox["h"])
            if w < 10 or h < 10:
                continue
            x2, y2 = min(x1 + w, frame.shape[1] - 1), min(y1 + h, frame.shape[0] - 1)
            x1, y1 = max(x1, 0), max(y1, 0)
            crop = frame[y1:y2, x1:x2]
            if crop.size == 0:
                continue

            preds = await loop.run_in_executor(
                None,
                lambda: self._health_model(
                    crop, conf=conf_threshold, imgsz=640, verbose=False
                ),
            )
            if len(preds) == 0 or preds[0].boxes is None:
                continue

            top_conf = 0.0
            top_class = "unknown"
            for box in preds[0].boxes:
                c = float(box.conf[0])
                if c > top_conf:
                    top_conf = c
                    top_class = self._health_model.names[int(box.cls[0])]

            results.append({
                "track_id": d.get("track_id"),
                "global_id": d.get("global_id"),
                "class_name": d.get("class_name"),
                "health_class": top_class,
                "health_confidence": round(top_conf, 3),
                "health_score": round(top_conf * 100, 1),
            })
        return results

    def unload(self):
        self._health_model = None
        logger.info("Health model unloaded")


detector = HealthClassifier()
