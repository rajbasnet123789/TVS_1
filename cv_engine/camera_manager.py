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


def _format_go2rtc_src(rtsp_url: str) -> list[str]:
    """Format source URLs for go2rtc ingestion using robust RTSP TCP formats."""
    try:
        parsed = urllib.parse.urlparse(rtsp_url)
        user = parsed.username or "admin"
        password = parsed.password or ""
        host = parsed.hostname or "127.0.0.1"

        if rtsp_url.startswith("dvrip://"):
            params = urllib.parse.parse_qs(parsed.query)
            dvrip_ch = int(params.get("channel", ["0"])[0])
            rtsp_ch = dvrip_ch + 1
        elif "channel=" in rtsp_url:
            params = urllib.parse.parse_qs(parsed.query)
            rtsp_ch = int(params.get("channel", ["1"])[0])
            dvrip_ch = max(0, rtsp_ch - 1)
        elif "/ch" in parsed.path:
            import re
            m = re.search(r"ch0*(\d+)", parsed.path)
            rtsp_ch = int(m.group(1)) if m else 1
            dvrip_ch = max(0, rtsp_ch - 1)
        else:
            rtsp_ch = 1
            dvrip_ch = 0

        # Format B (ch0N/0) — newer TVS/XMEye firmware over TCP
        rtsp_fmt_b = f"ffmpeg:rtsp://{user}:{password}@{host}:554/ch{rtsp_ch:02d}/0#video=copy#transport=tcp"
        # Format A (user=...&channel=N) — legacy TVS/XMEye firmware over TCP
        rtsp_fmt_a = f"ffmpeg:rtsp://{user}:{password}@{host}:554/user={user}&password={password}&channel={rtsp_ch}&stream=0.sdp#video=copy#transport=tcp"
        # Native RTSP direct
        direct_fmt_b = f"rtsp://{user}:{password}@{host}:554/ch{rtsp_ch:02d}/0"
        direct_fmt_a = f"rtsp://{user}:{password}@{host}:554/user={user}&password={password}&channel={rtsp_ch}&stream=0.sdp"
        dvrip_fallback = f"dvrip://{user}:{password}@{host}:34567?channel={dvrip_ch}&subtype=0"

        return [rtsp_fmt_b, rtsp_fmt_a, direct_fmt_b, direct_fmt_a, dvrip_fallback, rtsp_url]
    except Exception:
        return [rtsp_url]


def _register_go2rtc_stream(camera_id: str, rtsp_url: str) -> str:
    """Register camera stream source in go2rtc via REST API and return go2rtc RTSP re-stream URL."""
    sources = _format_go2rtc_src(rtsp_url)
    primary_src = sources[0] if sources else rtsp_url

    # Method 1: PUT /api/streams?name=...&src=...
    try:
        query = urllib.parse.urlencode({"name": camera_id, "src": primary_src})
        url = f"{settings.GO2RTC_API_URL}/api/streams?{query}"
        req = urllib.request.Request(url, method="PUT")
        with urllib.request.urlopen(req, timeout=3) as resp:
            if resp.status in (200, 201):
                logger.info("Registered stream %s in go2rtc (PUT query: %s)", camera_id, primary_src)
                return f"{settings.GO2RTC_RTSP_URL}/{camera_id}"
    except Exception as e:
        logger.debug("go2rtc PUT query failed for %s: %s", camera_id, e)

    # Method 2: POST /api/streams with JSON payload {"name": camera_id, "src": sources}
    try:
        url = f"{settings.GO2RTC_API_URL}/api/streams"
        payload = json.dumps({"name": camera_id, "src": sources}).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            if resp.status in (200, 201):
                logger.info("Registered stream %s in go2rtc (POST json)", camera_id)
                return f"{settings.GO2RTC_RTSP_URL}/{camera_id}"
    except Exception as e:
        logger.warning("Failed to register stream %s in go2rtc: %s", camera_id, e)

    return f"{settings.GO2RTC_RTSP_URL}/{camera_id}"


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
