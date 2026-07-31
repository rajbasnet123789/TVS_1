import logging
import time
import typing

import cv2
import numpy as np
import torch
from ultralytics import YOLO

from cv_engine import frame_store
from cv_engine.config import settings
from cv_engine.object_tracker import ObjectTracker

logger = logging.getLogger(__name__)


def _worker_main(
    camera_id: str,
    farm_id: str,
    rtsp_url: str,
    roi_polygon: list[list[float]] | None,
    detection_queue: typing.Any,
    stop_event: typing.Any,
) -> None:
    logging.basicConfig(level=logging.INFO)

    cuda_available = torch.cuda.is_available()
    device = "cuda:0" if cuda_available else "cpu"
    logger.info(
        "CameraWorker starting for %s on device=%s (CUDA available: %s, Device count: %d)",
        camera_id,
        device,
        cuda_available,
        torch.cuda.device_count() if cuda_available else 0,
    )

    model = YOLO(settings.MODEL_PATH)
    model.to(device)
    tracker = ObjectTracker(model, device=device)
    from cv_engine.stream_manager import RtspCameraStream

    stream = RtspCameraStream(camera_id, rtsp_url)
    stream.start()

    frame_idx = 0
    backoff = 1.0
    max_backoff = 10.0
    min_interval = settings.INFERENCE_MIN_INTERVAL_MS / 1000.0
    last_inference_at = 0.0

    while not stop_event.is_set():
        raw = frame_store.latest_bytes(camera_id)
        if not raw:
            time.sleep(0.1)
            continue

        nparr = np.frombuffer(raw, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if frame is None:
            time.sleep(0.1)
            continue

        backoff = 1.0

        now = time.monotonic()
        if now - last_inference_at < min_interval:
            time.sleep(0.05)
            continue

        detections = tracker.track(
            frame,
            conf_threshold=settings.DETECTION_CONFIDENCE,
            imgsz=settings.INFERENCE_IMGSZ,
        )
        last_inference_at = now

        event_batch = []

        for det in detections:
            cx, cy, w, h = det["x"], det["y"], det["w"], det["h"]

            if roi_polygon is not None:
                contour = np.array(roi_polygon, dtype=np.float32)
                dist = cv2.pointPolygonTest(contour, (cx, cy), False)
                if dist < 0:
                    continue

            event_batch.append({
                "camera_id": camera_id,
                "farm_id": farm_id,
                "track_id": det["track_id"],
                "class_name": det["class_name"],
                "confidence": det["confidence"],
                "x": cx,
                "y": cy,
                "w": w,
                "h": h,
            })

        for event in event_batch:
            try:
                detection_queue.put_nowait(event)
            except Exception:
                pass

        # Publish a lightweight live-count event (skips InfluxDB; server pushes it
        # straight to the backend WebSocket so the UI updates in near-real-time).
        try:
            detection_queue.put_nowait({
                "type": "count",
                "camera_id": camera_id,
                "farm_id": farm_id,
                "count": len(event_batch),
                "ts": time.time(),
            })
        except Exception:
            pass

        frame_idx += 1
        time.sleep(0.01)

    stream.cleanup()
    logger.info("CameraWorker stopped for %s", camera_id)
