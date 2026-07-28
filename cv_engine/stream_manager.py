import logging
import struct
import subprocess
import threading
import time
from pathlib import Path

from cv_engine import frame_store

logger = logging.getLogger(__name__)


def normalize_url(url: str) -> tuple[str, bool]:
    if not url:
        return url, False
    if url.startswith("dvrip://"):
        import re
        match = re.match(r"dvrip://(?:([^:]+):([^@]+)@)?([^:/]+)(?::(\d+))?/(\d+)", url)
        if match:
            user, pwd, host, port, ch = match.groups()
            ch_num = int(ch)
            user_str = user or "admin"
            pwd_str = pwd or ""
            auth_str = f"{user_str}:{pwd_str}@" if user_str else ""
            return f"rtsp://{auth_str}{host}:554/user={user_str}&password={pwd_str}&channel={ch_num}&stream=0.sdp", True
    return url, url.startswith("rtsp://")


class RtspCameraStream:
    def __init__(self, camera_id: str, rtsp_url: str):
        self.camera_id = camera_id
        self.rtsp_url = rtsp_url
        self._process: subprocess.Popen | None = None
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._running = False

    @property
    def running(self) -> bool:
        return self._running

    def start(self) -> None:
        if self._running:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._capture_loop,
            daemon=True,
            name=f"rtsp-{self.camera_id}",
        )
        self._thread.start()
        self._running = True
        logger.info("RTSP stream started for camera %s", self.camera_id)

    def stop(self) -> None:
        self._stop_event.set()
        self._running = False
        if self._process and self._process.poll() is None:
            try:
                self._process.terminate()
                self._process.wait(timeout=5)
            except Exception:
                try:
                    self._process.kill()
                except Exception:
                    pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        logger.info("RTSP stream stopped for camera %s", self.camera_id)

    def _capture_loop(self) -> None:
        backoff = 1
        max_backoff = 30
        while not self._stop_event.is_set():
            try:
                self._run_ffmpeg()
            except Exception as e:
                if self._stop_event.is_set():
                    break
                logger.warning(
                    "FFmpeg crashed for camera %s: %s, retrying in %ds",
                    self.camera_id, e, backoff,
                )
            if self._stop_event.is_set():
                break
            time.sleep(backoff)
            backoff = min(backoff * 2, max_backoff)
        logger.info("Capture loop exited for camera %s", self.camera_id)

    def _run_ffmpeg(self) -> None:
        target_url, is_rtsp = normalize_url(self.rtsp_url)
        cmd = ["ffmpeg"]
        if is_rtsp:
            cmd.extend(["-rtsp_transport", "tcp"])
        cmd.extend([
            "-i", target_url,
            "-f", "mjpeg",
            "-q:v", "3",
            "-r", "25",
            "pipe:1",
        ])
        self._process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
        )

        soi = b"\xff\xd8"
        eoi = b"\xff\xd9"
        buffer = b""
        try:
            while not self._stop_event.is_set():
                chunk = self._process.stdout.read(65536)
                if not chunk:
                    break
                buffer += chunk
                while True:
                    soi_idx = buffer.find(soi)
                    if soi_idx == -1:
                        buffer = b""
                        break
                    if soi_idx > 0:
                        buffer = buffer[soi_idx:]
                    eoi_idx = buffer.find(eoi, 2)
                    if eoi_idx == -1:
                        break
                    frame = buffer[: eoi_idx + 2]
                    buffer = buffer[eoi_idx + 2:]
                    frame_store.publish(self.camera_id, frame)
        finally:
            if self._process:
                err = ""
                if self._process.stderr:
                    try:
                        err = self._process.stderr.read().decode("utf-8", errors="replace")[-300:]
                    except Exception:
                        pass
                if err and not self._stop_event.is_set():
                    logger.warning("FFmpeg process log for %s: %s", self.camera_id, err.strip())
                if self._process.poll() is None:
                    try:
                        self._process.terminate()
                        self._process.wait(timeout=3)
                    except Exception:
                        pass

    def cleanup(self) -> None:
        self.stop()
        Path(frame_store._raw_path(self.camera_id)).unlink(missing_ok=True)
        Path(frame_store._annotated_path(self.camera_id)).unlink(missing_ok=True)
