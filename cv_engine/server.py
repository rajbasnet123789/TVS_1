import asyncio
import logging
import multiprocessing
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from cv_engine.camera_manager import CameraManager
from cv_engine.config import settings
from cv_engine.influx_writer import InfluxWriter
from cv_engine.xmeye_scan import scan_xmeye_lan

from typing import Any

logger = logging.getLogger(__name__)

_influx_writer: InfluxWriter | None = None
_camera_manager: CameraManager | None = None
_detection_queue: Any = None


async def _report_camera_statuses() -> None:
    """Report which camera workers are running back to the backend so camera.status is kept accurate in PostgreSQL."""
    if _camera_manager is None:
        return
    headers: dict[str, str] = {}
    if settings.CV_ENGINE_API_KEY:
        headers["X-Internal-Token"] = settings.CV_ENGINE_API_KEY

    worker_status = _camera_manager.get_status()
    running_ids = [cid for cid, info in worker_status.items() if info.get("running")]
    stopped_ids = [cid for cid, info in worker_status.items() if not info.get("running")]

    try:
        async with httpx.AsyncClient(timeout=5) as client:
            await client.patch(
                f"{settings.BUSINESS_BACKEND_URL}/v1/internal/cameras/status",
                headers={**headers, "Content-Type": "application/json"},
                json={"running": running_ids, "stopped": stopped_ids},
            )
    except Exception as e:
        logger.warning("Failed to report camera statuses: %s", e)


async def _sync_cameras_loop() -> None:
    backoff = 1.0
    max_backoff = 30.0
    headers: dict[str, str] = {}
    if settings.CV_ENGINE_API_KEY:
        headers["X-Internal-Token"] = settings.CV_ENGINE_API_KEY
    while True:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{settings.BUSINESS_BACKEND_URL}/v1/internal/cameras",
                    headers=headers
                )
                resp.raise_for_status()
                cameras = resp.json().get("cameras", [])
                _camera_manager.sync_cameras(cameras)
                backoff = 1.0
                # Report running/stopped workers back to backend so camera.status stays accurate
                await _report_camera_statuses()
        except Exception as e:
            logger.warning("Camera sync failed: %s, retrying in %.0fs", e, backoff)
            backoff = min(backoff * 2, max_backoff)
        await asyncio.sleep(max(backoff, 10))


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _influx_writer, _camera_manager, _detection_queue

    _detection_queue = multiprocessing.Queue(maxsize=5000)
    _influx_writer = InfluxWriter()
    _influx_writer.start()

    _camera_manager = CameraManager(_detection_queue)

    sync_task = asyncio.create_task(_sync_cameras_loop())
    drain_task = asyncio.create_task(_drain_detection_queue())

    yield

    sync_task.cancel()
    drain_task.cancel()
    _camera_manager.stop_all()
    _influx_writer.stop()


async def _drain_detection_queue() -> None:
    while True:
        try:
            while not _detection_queue.empty():
                event = _detection_queue.get_nowait()
                _influx_writer.enqueue(event)
        except Exception:
            pass
        await asyncio.sleep(0.05)


app = FastAPI(title="CV Engine", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/status")
async def status():
    return {"cameras": _camera_manager.get_status() if _camera_manager else {}}


@app.post("/xmeye-scan")
async def xmeye_scan(timeout: float = 5.0):
    try:
        devices = await scan_xmeye_lan(timeout=timeout)
        return {"devices": devices, "count": len(devices)}
    except Exception as exc:
        logger.error("XMEye LAN scan error: %s", exc)
        return JSONResponse(
            status_code=502,
            content={"detail": f"XMEye LAN scan failed: {exc}"},
        )
