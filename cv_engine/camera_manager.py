import logging
import multiprocessing
import time
import typing

import urllib.parse
import urllib.request

from cv_engine.camera_worker import _worker_main
from cv_engine import frame_store
from cv_engine.config import settings

logger = logging.getLogger(__name__)


import json


def _register_go2rtc_stream(camera_id: str, rtsp_url: str) -> str:
    """Register camera stream source in go2rtc via REST API and return go2rtc RTSP re-stream URL."""
    # Method 1: POST /api/streams?name=...&src=...
    try:
        query = urllib.parse.urlencode({"name": camera_id, "src": rtsp_url})
        url = f"{settings.GO2RTC_API_URL}/api/streams?{query}"
        req = urllib.request.Request(url, method="POST")
        with urllib.request.urlopen(req, timeout=3) as resp:
            if resp.status in (200, 201):
                logger.debug("Registered stream %s in go2rtc (POST query)", camera_id)
                return f"{settings.GO2RTC_RTSP_URL}/{camera_id}"
    except Exception:
        pass

    # Method 2: PUT /api/streams?name=...&src=...
    try:
        query = urllib.parse.urlencode({"name": camera_id, "src": rtsp_url})
        url = f"{settings.GO2RTC_API_URL}/api/streams?{query}"
        req = urllib.request.Request(url, method="PUT")
        with urllib.request.urlopen(req, timeout=3) as resp:
            if resp.status in (200, 201):
                logger.debug("Registered stream %s in go2rtc (PUT query)", camera_id)
                return f"{settings.GO2RTC_RTSP_URL}/{camera_id}"
    except Exception:
        pass

    # Method 3: Form-urlencoded POST /api/streams
    try:
        url = f"{settings.GO2RTC_API_URL}/api/streams"
        data = urllib.parse.urlencode({"name": camera_id, "src": rtsp_url}).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            if resp.status in (200, 201):
                logger.debug("Registered stream %s in go2rtc (Form POST)", camera_id)
                return f"{settings.GO2RTC_RTSP_URL}/{camera_id}"
    except Exception as e:
        logger.warning("Failed to register stream %s in go2rtc (%s), falling back to direct RTSP", camera_id, e)

    return rtsp_url


class CameraManager:
    def __init__(self, detection_queue: typing.Any):
        self._detection_queue = detection_queue
        self._workers: dict[str, typing.Any] = {}
        self._stop_events: dict[str, typing.Any] = {}

    def sync_cameras(self, cameras: list[dict]) -> None:
        # Register all active cameras in go2rtc on every sync loop
        for cam in cameras:
            _register_go2rtc_stream(cam["id"], cam["rtsp_url"])

        desired_ids = {c["id"] for c in cameras}
        current_ids = set(self._workers.keys())

        to_stop = current_ids - desired_ids
        to_start = desired_ids - current_ids
        to_update = current_ids & desired_ids

        for cam_id in to_stop:
            self.stop_camera(cam_id)

        cam_by_id = {c["id"]: c for c in cameras}
        for cam_id in to_start:
            cam = cam_by_id[cam_id]
            self.start_camera(cam)

        for cam_id in to_update:
            cam = cam_by_id[cam_id]
            if not self._workers[cam_id].is_alive():
                self.stop_camera(cam_id)
                self.start_camera(cam)

        logger.info(
            "Camera sync: %d running, %d started, %d stopped",
            len(self._workers), len(to_start), len(to_stop),
        )

    def start_camera(self, camera_config: dict) -> None:
        camera_id = camera_config["id"]
        if camera_id in self._workers and self._workers[camera_id].is_alive():
            return

        # Register stream in go2rtc and get the go2rtc re-stream URL
        rtsp_target = _register_go2rtc_stream(camera_id, camera_config["rtsp_url"])

        stop_event = multiprocessing.Event()
        proc = multiprocessing.Process(
            target=_worker_main,
            args=(
                camera_id,
                camera_config.get("farm_id", ""),
                rtsp_target,
                camera_config.get("roi"),
                self._detection_queue,
                stop_event,
            ),
            daemon=True,
            name=f"worker-{camera_id}",
        )
        proc.start()
        self._workers[camera_id] = proc
        self._stop_events[camera_id] = stop_event
        logger.info("Started camera worker for %s (target: %s)", camera_id, rtsp_target)

    def stop_camera(self, camera_id: str) -> None:
        if camera_id not in self._workers:
            return

        stop_event = self._stop_events.pop(camera_id, None)
        proc = self._workers.pop(camera_id, None)

        if stop_event:
            stop_event.set()

        if proc and proc.is_alive():
            proc.join(timeout=5)
            if proc.is_alive():
                proc.terminate()
                proc.join(timeout=3)

        frame_store.publish(camera_id, b"")
        frame_store.publish_annotated(camera_id, b"")
        logger.info("Stopped camera worker for %s", camera_id)

    def stop_all(self) -> None:
        for cam_id in list(self._workers.keys()):
            self.stop_camera(cam_id)

    def get_status(self) -> dict[str, dict]:
        return {
            cam_id: {
                "running": proc.is_alive(),
                "pid": proc.pid,
            }
            for cam_id, proc in self._workers.items()
        }
