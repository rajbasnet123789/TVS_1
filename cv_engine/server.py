import asyncio
import json
import logging
import multiprocessing
import time
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.responses import StreamingResponse
from jose import JWTError, jwt

from cv_engine import frame_store
from cv_engine.alert_client import AlertEvaluator
from cv_engine.camera_manager import CameraManager
from cv_engine.config import settings
from cv_engine.influx_writer import InfluxWriter

logger = logging.getLogger(__name__)

_influx_writer: InfluxWriter | None = None
_camera_manager: CameraManager | None = None
_alert_evaluator: AlertEvaluator | None = None
_detection_queue: multiprocessing.Queue | None = None


def _validate_token(token: str) -> dict | None:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        if payload.get("exp") and payload["exp"] < time.time():
            return None
        return payload
    except JWTError:
        return None


async def _sync_cameras_loop() -> None:
    backoff = 1.0
    max_backoff = 30.0
    while True:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{settings.BUSINESS_BACKEND_URL}/v1/internal/cameras"
                )
                resp.raise_for_status()
                cameras = resp.json().get("cameras", [])
                _camera_manager.sync_cameras(cameras)
                backoff = 1.0
        except Exception as e:
            logger.warning("Camera sync failed: %s, retrying in %.0fs", e, backoff)
            backoff = min(backoff * 2, max_backoff)
        await asyncio.sleep(max(backoff, 10))


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _influx_writer, _camera_manager, _alert_evaluator, _detection_queue

    _detection_queue = multiprocessing.Queue(maxsize=5000)
    _influx_writer = InfluxWriter()
    _influx_writer.start()

    _camera_manager = CameraManager(_detection_queue)
    _alert_evaluator = AlertEvaluator()
    _alert_evaluator.start()

    sync_task = asyncio.create_task(_sync_cameras_loop())
    drain_task = asyncio.create_task(_drain_detection_queue())

    yield

    sync_task.cancel()
    drain_task.cancel()
    _camera_manager.stop_all()
    _alert_evaluator.stop()
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


@app.websocket("/cvws/{camera_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    camera_id: str,
    token: str = Query(...),
):
    payload = _validate_token(token)
    if payload is None:
        await websocket.close(code=4001, reason="Invalid or expired token")
        return

    await websocket.accept()
    poll_interval = settings.WS_POLL_INTERVAL_MS / 1000.0
    last_frame_mtime = 0.0
    last_meta_mtime = 0.0

    try:
        while True:
            frame_mtime = frame_store.latest_mtime(camera_id, annotated=True)
            if frame_mtime > last_frame_mtime:
                last_frame_mtime = frame_mtime
                frame = frame_store.latest_bytes(camera_id, annotated=True)
                if frame:
                    await websocket.send_bytes(frame)

            meta_mtime = frame_store.metadata_mtime(camera_id)
            if meta_mtime > last_meta_mtime:
                last_meta_mtime = meta_mtime
                meta = frame_store.latest_metadata(camera_id)
                if meta:
                    msg = {k: v for k, v in meta.items() if k != "_mtime"}
                    await websocket.send_text(json.dumps(msg))

            await asyncio.sleep(poll_interval)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error("WebSocket error for %s: %s", camera_id, e)
    finally:
        try:
            await websocket.close()
        except Exception:
            pass


@app.get("/mjpeg/{camera_id}")
async def mjpeg_stream(camera_id: str):
    async def generate():
        boundary = "--mjpegboundary"
        last_mtime = 0.0
        while True:
            mtime = frame_store.latest_mtime(camera_id, annotated=True)
            if mtime > last_mtime:
                last_mtime = mtime
                frame = frame_store.latest_bytes(camera_id, annotated=True)
                if frame:
                    yield (
                        f"--{boundary}\r\n"
                        "Content-Type: image/jpeg\r\n"
                        f"Content-Length: {len(frame)}\r\n\r\n"
                    ).encode() + frame + b"\r\n"
            await asyncio.sleep(0.05)

    return StreamingResponse(
        generate(),
        media_type="multipart/x-mixed-replace; boundary=mjpegboundary",
    )
