import logging
import multiprocessing
import time

import cv2
import numpy as np
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
    detection_queue: multiprocessing.Queue,
    stop_event: multiprocessing.Event,
) -> None:
    logging.basicConfig(level=logging.INFO)
    logger.info("CameraWorker started for %s", camera_id)

    model = YOLO(settings.MODEL_PATH)
    tracker = ObjectTracker(model)
    from cv_engine.stream_manager import RtspCameraStream

    stream = RtspCameraStream(camera_id, rtsp_url)
    stream.start()

    frame_idx = 0
    backoff = 1.0
    max_backoff = 10.0

    while not stop_event.is_set():
        raw = frame_store.latest_bytes(camera_id, annotated=False)
        if raw is None:
            time.sleep(0.1)
            continue

        nparr = np.frombuffer(raw, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if frame is None:
            time.sleep(0.1)
            continue

        backoff = 1.0

        detections = tracker.track(
            frame,
            conf_threshold=settings.DETECTION_CONFIDENCE,
        )

        annotated = frame.copy()
        event_batch = []

        for det in detections:
            cx, cy, w, h = det["x"], det["y"], det["w"], det["h"]
            x1 = int(cx - w / 2)
            y1 = int(cy - h / 2)
            x2 = int(cx + w / 2)
            y2 = int(cy + h / 2)

            if roi_polygon is not None:
                contour = np.array(roi_polygon, dtype=np.float32)
                dist = cv2.pointPolygonTest(contour, (cx, cy), False)
                if dist < 0:
                    continue

            color = (0, 255, 0)
            cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
            label = f"ID:{det['track_id']} {det['class_name']} {det['confidence']:.2f}"
            cv2.putText(
                annotated, label, (x1, y1 - 10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1,
            )

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

        _, buf = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 85])
        frame_store.publish_annotated(camera_id, buf.tobytes())

        frame_store.publish_metadata(camera_id, {
            "type": "detections",
            "camera_id": camera_id,
            "width": frame.shape[1],
            "height": frame.shape[0],
            "detections": [
                {
                    "track_id": d["track_id"],
                    "class_name": d["class_name"],
                    "confidence": round(d["confidence"], 3),
                    "bbox": {
                        "x": round(d["x"] - d["w"] / 2, 1),
                        "y": round(d["y"] - d["h"] / 2, 1),
                        "w": round(d["w"], 1),
                        "h": round(d["h"], 1),
                    },
                }
                for d in event_batch
            ],
            "_mtime": time.time(),
        })

        for event in event_batch:
            try:
                detection_queue.put_nowait(event)
            except Exception:
                pass

        frame_idx += 1
        time.sleep(0.01)

    stream.cleanup()
    logger.info("CameraWorker stopped for %s", camera_id)
