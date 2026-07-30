import logging
import torch
from ultralytics import YOLO

logger = logging.getLogger(__name__)


class ObjectTracker:
    def __init__(self, model: YOLO, device: str | None = None):
        self._model = model
        if device is None:
            self._device = "cuda:0" if torch.cuda.is_available() else "cpu"
        else:
            self._device = device
        
        # Use FP16 half-precision inference on GPU for maximum throughput & lower VRAM
        self._half = (self._device != "cpu")
        logger.info("ObjectTracker initialized on device=%s (half-precision FP16=%s)", self._device, self._half)

    def track(
        self,
        frame,
        conf_threshold: float = 0.55,
        classes: list[int] | None = None,
    ):
        results = self._model.track(
            source=frame,
            persist=True,
            conf=conf_threshold,
            classes=classes,
            tracker="bytetrack.yaml",
            device=self._device,
            half=self._half,
            verbose=False,
        )
        if not results or results[0] is None:
            return []

        result = results[0]
        detections = []
        if result.boxes is not None and result.boxes.id is not None:
            ids = result.boxes.id.cpu().numpy()
            boxes = result.boxes.xywh.cpu().numpy()
            confs = result.boxes.conf.cpu().numpy()
            clss = result.boxes.cls.cpu().numpy()
            for i in range(len(ids)):
                detections.append({
                    "track_id": int(ids[i]),
                    "x": float(boxes[i][0]),
                    "y": float(boxes[i][1]),
                    "w": float(boxes[i][2]),
                    "h": float(boxes[i][3]),
                    "confidence": float(confs[i]),
                    "class_id": int(clss[i]),
                    "class_name": result.names[int(clss[i])],
                })
        return detections

