import asyncio
import logging
from datetime import datetime, timezone

import cv2
import numpy as np

from app.cameras.models import Camera
from app.config import settings
from app.database import async_session
from app.detection.detector import detector
from app.detection.tracker import tracker
from app.detection.mcmt.tracker import GlobalTracker
from app.websocket.manager import manager

logger = logging.getLogger(__name__)


class CameraDetectionWorker:
    def __init__(self, camera: Camera, global_tracker: GlobalTracker | None = None):
        self.camera = camera
        self._global_tracker = global_tracker
        self._task: asyncio.Task | None = None
        self._running = False
        self._frame_count = 0
        self._cap: cv2.VideoCapture | None = None

    @property
    def is_running(self) -> bool:
        return self._running

    async def start(self):
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run())
        logger.info(f"Detection started for camera: {self.camera.name}")

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        self._release_rtsp()
        await self._update_status("offline")
        logger.info(f"Detection stopped for camera: {self.camera.name}")

    def _release_rtsp(self):
        if self._cap:
            self._cap.release()
            self._cap = None

    async def _update_status(self, status: str):
        try:
            async with async_session() as session:
                from sqlalchemy import select
                result = await session.execute(select(Camera).where(Camera.id == self.camera.id))
                cam = result.scalar_one_or_none()
                if cam and cam.status != status:
                    cam.status = status
                    await session.commit()
                    logger.info(f"Camera status updated: {self.camera.name} -> {status}")
        except Exception as e:
            logger.warning(f"Failed to update camera status: {e}")

    async def _get_frame(self) -> np.ndarray | None:
        if self._cap is None:
            loop = asyncio.get_event_loop()
            self._cap = await loop.run_in_executor(
                None, lambda: cv2.VideoCapture(self.camera.rtsp_url)
            )
            if not self._cap or not self._cap.isOpened():
                logger.error(f"Failed to open RTSP: {self.camera.name}")
                self._cap = None
                return None
            logger.info(f"RTSP connected: {self.camera.name}")
            await self._update_status("online")

        loop = asyncio.get_event_loop()
        ret, frame = await loop.run_in_executor(None, lambda: self._cap.read())
        if not ret:
            self._release_rtsp()
            return None
        return frame

    def _should_detect(self) -> bool:
        return self._frame_count % 3 == 0

    async def _detect_and_track(self, frame: np.ndarray) -> list[dict]:
        detections = await detector.detect(frame)
        if not detections:
            return []

        tracked = await tracker.update(detections, frame)

        if self._global_tracker is not None:
            track_ids = [d.get("track_id") for d in tracked]
            loop = asyncio.get_running_loop()
            mcmt_results = await loop.run_in_executor(
                None,
                lambda: self._global_tracker.process_frame(
                    detections=tracked,
                    track_ids=track_ids,
                    frame=frame,
                    camera_id=str(self.camera.id),
                ),
            )
            return mcmt_results

        return tracked

    async def _store_detections(self, detections: list[dict]):
        try:
            from influxdb_client import InfluxDBClient
            from influxdb_client.client.write_api import SYNCHRONOUS

            client = InfluxDBClient(
                url=settings.influx_url,
                token=settings.influx_token,
                org=settings.influx_org,
            )
            write_api = client.write_api(write_options=SYNCHRONOUS)
            points = []
            for d in detections:
                tags = {
                    "camera_id": str(self.camera.id),
                    "class_name": d["class_name"],
                    "track_id": str(d.get("track_id", "-1")),
                }
                global_id = d.get("global_id")
                if global_id is not None:
                    tags["global_id"] = str(global_id)

                points.append({
                    "measurement": "detections",
                    "tags": tags,
                    "fields": {
                        "confidence": float(d["confidence"]),
                        "x": float(d["bbox"]["x"]),
                        "y": float(d["bbox"]["y"]),
                        "w": float(d["bbox"]["w"]),
                        "h": float(d["bbox"]["h"]),
                    },
                    "time": datetime.now(timezone.utc),
                })
            if points:
                from influxdb_client.rest import ApiException
                try:
                    write_api.write(bucket=settings.influx_bucket, record=points)
                except (ApiException, Exception) as e:
                    logger.warning(f"InfluxDB write error: {e}")
            client.close()
        except ImportError:
            pass
        except Exception as e:
            logger.warning(f"InfluxDB error: {e}")

    async def _publish_detections(self, detections: list[dict]):
        event = {
            "type": "detection",
            "camera_id": str(self.camera.id),
            "camera_name": self.camera.name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "detections": [
                {
                    "class_name": d["class_name"],
                    "confidence": round(d["confidence"], 3),
                    "track_id": d.get("track_id"),
                    "global_id": d.get("global_id"),
                    "bbox": d["bbox"],
                }
                for d in detections
            ],
        }
        await manager.broadcast("detections", event)

    async def _run(self):
        await detector.load()
        await tracker.load()
        if self._global_tracker is not None:
            await self._global_tracker.load()

        while self._running:
            try:
                frame = await self._get_frame()
                if frame is None:
                    await asyncio.sleep(1)
                    self._frame_count = 0
                    continue

                self._frame_count += 1

                if self._should_detect():
                    detections = await self._detect_and_track(frame)
                    if detections:
                        asyncio.ensure_future(self._store_detections(detections))
                        await self._publish_detections(detections)

                await asyncio.sleep(0.1)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Detection error for {self.camera.name}: {e}", exc_info=True)
                await asyncio.sleep(2)

        self._release_rtsp()


class DetectionOrchestrator:
    def __init__(self):
        self._workers: dict[str, CameraDetectionWorker] = {}
        self._global_tracker = GlobalTracker(
            match_threshold=0.5,
            spatial_constraint_distance=50.0,
            temporal_constraint_seconds=5.0,
        )
        self._cleanup_task: asyncio.Task | None = None

    @property
    def global_tracker(self) -> GlobalTracker:
        return self._global_tracker

    async def start_camera(self, camera: Camera):
        if str(camera.id) in self._workers:
            return
        worker = CameraDetectionWorker(camera, global_tracker=self._global_tracker)
        self._workers[str(camera.id)] = worker
        await worker.start()
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._periodic_cleanup())

    async def stop_camera(self, camera_id: str):
        worker = self._workers.pop(camera_id, None)
        if worker:
            await worker.stop()

    async def stop_all(self):
        for camera_id in list(self._workers.keys()):
            await self.stop_camera(camera_id)
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None

    async def _periodic_cleanup(self):
        while True:
            try:
                await asyncio.sleep(300)
                self._global_tracker.cleanup_stale(max_age_seconds=600)
                identities = self._global_tracker.get_active_identities(max_age_seconds=60)
                if identities:
                    await manager.broadcast("identities", {
                        "type": "identity_update",
                        "active_count": len(identities),
                        "total_count": self._global_tracker.get_total_identities(),
                        "identities": [
                            {
                                "global_id": ident["global_id"],
                                "camera_id": ident["camera_id"],
                                "confidence": round(ident["confidence"], 3),
                            }
                            for ident in identities[:50]
                        ],
                    })
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"Cleanup task error: {e}")

    def get_status(self, camera_id: str) -> bool:
        worker = self._workers.get(camera_id)
        return worker.is_running if worker else False

    def list_active(self) -> list[str]:
        return [cid for cid, w in self._workers.items() if w.is_running]


orchestrator = DetectionOrchestrator()
