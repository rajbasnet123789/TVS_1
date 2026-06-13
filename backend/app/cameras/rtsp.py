import cv2
import asyncio
import logging

from app.cameras.models import Camera

logger = logging.getLogger(__name__)


class RTSPFrameGrabber:
    def __init__(self, camera: Camera):
        self.camera = camera
        self.cap: cv2.VideoCapture | None = None
        self._running = False

    async def connect(self):
        loop = asyncio.get_event_loop()
        self.cap = await loop.run_in_executor(None, lambda: cv2.VideoCapture(self.camera.rtsp_url))
        if not self.cap.isOpened():
            logger.error(f"Failed to open RTSP stream for {self.camera.name}")
            return False
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        logger.info(f"Connected to RTSP stream: {self.camera.name}")
        return True

    async def read_frame(self):
        if not self.cap or not self.cap.isOpened():
            return None
        loop = asyncio.get_event_loop()
        ret, frame = await loop.run_in_executor(None, lambda: self.cap.read())
        if ret:
            return frame
        return None

    async def reconnect(self, max_retries=3, delay=5):
        self.release()
        for attempt in range(max_retries):
            logger.info(f"Reconnecting to {self.camera.name} (attempt {attempt + 1}/{max_retries})")
            if await self.connect():
                return True
            await asyncio.sleep(delay)
        return False

    def release(self):
        if self.cap:
            self.cap.release()
            self.cap = None
            logger.info(f"Released RTSP connection: {self.camera.name}")
