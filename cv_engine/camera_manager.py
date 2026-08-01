import logging
import multiprocessing
import time
import typing

import urllib.error
import urllib.parse
import urllib.request

from cv_engine.camera_worker import _worker_main
from cv_engine import frame_store
from cv_engine.config import settings

logger = logging.getLogger(__name__)


def _is_go2rtc_source(rtsp_url: str) -> bool:
    """Return True when the URL already points at the local go2rtc restream server."""
    return any(k in rtsp_url for k in ("8554", "localhost", "127.0.0.1", "go2rtc"))


def _format_go2rtc_src(rtsp_url: str) -> list[str]:
    """Format comprehensive producer URL fallback list for go2rtc ingestion."""
    try:
        parsed = urllib.parse.urlparse(rtsp_url)
        user = parsed.username or "admin"
        password = parsed.password or ""
        host = parsed.hostname or "127.0.0.1"

        # Extract 0-indexed channel (0, 1, 2, 3, 4...)
        dvrip_ch = 0
        if rtsp_url.startswith("dvrip://"):
            parts = parsed.path.strip("/").split("/")
            if parts and parts[0].isdigit():
                dvrip_ch = int(parts[0])
            elif "channel=" in rtsp_url:
                params = urllib.parse.parse_qs(parsed.query)
                dvrip_ch = int(params.get("channel", ["0"])[0])
        elif "channel=" in rtsp_url:
            params = urllib.parse.parse_qs(parsed.query)
            ch_val = int(params.get("channel", ["1"])[0])
            dvrip_ch = max(0, ch_val - 1) if "realmonitor" not in rtsp_url else ch_val
        elif "/ch" in parsed.path:
            import re
            m = re.search(r"ch0*(\d+)", parsed.path)
            if m:
                dvrip_ch = max(0, int(m.group(1)) - 1)

        rtsp_ch = dvrip_ch + 1

        # Comprehensive Multi-Producer Fallback List — ?channel= query string MUST be first for go2rtc DVRIP module
        p1_dvrip_query = f"dvrip://{user}:{password}@{host}:34567?channel={dvrip_ch}&subtype=0"
        p2_dvrip_path = f"dvrip://{user}:{password}@{host}:34567/{dvrip_ch}"
        p3_rtsp_realmonitor = f"ffmpeg:rtsp://{user}:{password}@{host}:554/cam/realmonitor?channel={dvrip_ch}&subtype=0#video=copy#transport=tcp"
        p4_rtsp_fmt_a = f"ffmpeg:rtsp://{user}:{password}@{host}:554/user={user}&password={password}&channel={rtsp_ch}&stream=0.sdp#video=copy#transport=tcp"
        p5_rtsp_fmt_b = f"ffmpeg:rtsp://{user}:{password}@{host}:554/ch{rtsp_ch:02d}/0#video=copy#transport=tcp"

        return [p1_dvrip_query, p2_dvrip_path, p3_rtsp_realmonitor, p4_rtsp_fmt_a, p5_rtsp_fmt_b, rtsp_url]
    except Exception:
        return [rtsp_url]


def _register_go2rtc_stream(camera_id: str, rtsp_url: str) -> bool:
    """Register the camera source in go2rtc via REST API.

    Returns True when go2rtc will serve the stream over RTSP at
    ``{GO2RTC_RTSP_URL}/{camera_id}``. go2rtc creates the stream in-memory even
    when its config file is mounted read-only (it fails to persist and returns
    HTTP 400 — that is NOT a registration failure, the stream still works).
    """
    if _is_go2rtc_source(rtsp_url):
        return True

    sources = _format_go2rtc_src(rtsp_url)
    primary_src = sources[0] if sources else rtsp_url

    try:
        query = urllib.parse.urlencode({"name": camera_id, "src": primary_src})
        url = f"{settings.GO2RTC_API_URL}/api/streams?{query}"
        req = urllib.request.Request(url, method="PUT")
        with urllib.request.urlopen(req, timeout=3) as resp:
            if resp.status in (200, 201):
                logger.info("Registered stream %s in go2rtc", camera_id)
                return True
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", errors="replace").strip()
        except Exception:
            pass
        if e.code == 400 and "read-only" in body:
            # Stream was created in-memory; only the config-file write failed.
            logger.info("Registered stream %s in go2rtc (in-memory, config read-only)", camera_id)
            return True
        logger.warning("Failed to register stream %s in go2rtc (HTTP %s): %s", camera_id, e.code, body or e)
    except Exception as e:
        logger.warning("Failed to register stream %s in go2rtc: %s", camera_id, e)
    return False


class CameraManager:
    def __init__(self, detection_queue: typing.Any):
        self._detection_queue = detection_queue
        self._workers: dict[str, typing.Any] = {}
        self._stop_events: dict[str, typing.Any] = {}
        # go2rtc registration state per camera: source last registered, last
        # result, and when that registration was attempted.
        self._go2rtc_source: dict[str, str] = {}
        self._go2rtc_ok: dict[str, bool] = {}
        self._go2rtc_attempt: dict[str, float] = {}

    def _go2rtc_target(self, camera_id: str, rtsp_url: str) -> str:
        """Return the URL the worker should open to reach this camera's stream."""
        if _is_go2rtc_source(rtsp_url):
            return rtsp_url
        return f"{settings.GO2RTC_RTSP_URL}/{camera_id}"

    def _ensure_go2rtc_streams(self, cameras: list[dict]) -> None:
        """Register camera sources in go2rtc, but only when needed.

        Registration only happens when the source changed, the previous attempt
        failed (with backoff), or the registration is stale (go2rtc may have
        restarted and lost its in-memory streams). This replaces the old
        behaviour of re-registering every camera on every sync, which spammed
        the logs with failures for cameras whose go2rtc config is read-only.
        """
        now = time.monotonic()
        refresh = settings.GO2RTC_REGISTER_REFRESH_SECONDS
        failure_backoff = 30.0
        for cam in cameras:
            cam_id = cam["id"]
            source = cam.get("rtsp_url", "")
            if _is_go2rtc_source(source):
                continue
            prev = self._go2rtc_source.get(cam_id)
            last = self._go2rtc_attempt.get(cam_id, 0.0)
            ok = self._go2rtc_ok.get(cam_id, False)
            changed = prev != source
            failed_recently = not ok and (now - last) >= failure_backoff
            stale = (now - last) >= refresh
            if not (changed or failed_recently or stale):
                continue
            registered = _register_go2rtc_stream(cam_id, source)
            self._go2rtc_source[cam_id] = source
            self._go2rtc_ok[cam_id] = registered
            self._go2rtc_attempt[cam_id] = now

    def sync_cameras(self, cameras: list[dict]) -> None:
        # Ensure every camera has a (re)registered go2rtc stream before workers
        # start pulling from it.
        self._ensure_go2rtc_streams(cameras)

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

        # Stream is registered in go2rtc by _ensure_go2rtc_streams; the worker
        # pulls the go2rtc re-stream URL (or the original URL if it already is one).
        rtsp_target = self._go2rtc_target(camera_id, camera_config.get("rtsp_url", ""))

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
