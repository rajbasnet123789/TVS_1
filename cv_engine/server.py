import asyncio
import json
import logging
import multiprocessing
import time
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.responses import JSONResponse, Response, StreamingResponse
from jose import JWTError, jwt

from cv_engine import frame_store
from cv_engine.camera_manager import CameraManager
from cv_engine.config import settings
from cv_engine.influx_writer import InfluxWriter
# XMEye discovery runs here because cv-engine has network_mode:host
# and can broadcast UDP to the physical LAN. Backend (bridge network) cannot.
from cv_engine.xmeye_scan import scan_xmeye_lan

from typing import Any

logger = logging.getLogger(__name__)

_influx_writer: InfluxWriter | None = None
_camera_manager: CameraManager | None = None
_detection_queue: Any = None


def _validate_token(token: str) -> dict | None:
    if not token or token == "null":
        logger.warning("WS token validation failed: token is empty or string 'null'")
        return None
    try:
        secret = settings.JWT_SECRET.strip()
        payload = jwt.decode(token, secret, algorithms=[settings.JWT_ALGORITHM])
        if payload.get("exp") and payload["exp"] < time.time():
            logger.warning("WS token validation failed: token expired (exp=%s, now=%s)", payload.get("exp"), time.time())
            return None
        return payload
    except JWTError as e:
        logger.warning(
            "WS token validation failed (JWTError): %s | secret_len=%d, token_prefix=%s",
            e, len(settings.JWT_SECRET), token[:20] if token else "None"
        )
        return None
    except Exception as e:
        logger.error("WS token validation unexpected error: %s", e)
        return None


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
    """
    UDP broadcast scan for XMEye/DVRIP NVRs on the local LAN.

    Must run here (cv-engine, network_mode:host) because Docker bridge
    blocks UDP broadcasts from reaching the physical network.
    Called by the backend /xmeye/scan endpoint which proxies here.
    """
    try:
        devices = await scan_xmeye_lan(timeout=timeout)
        return {"devices": devices, "count": len(devices)}
    except Exception as exc:
        logger.error("XMEye LAN scan error: %s", exc)
        return JSONResponse(
            status_code=502,
            content={"detail": f"XMEye LAN scan failed: {exc}"},
        )


@app.websocket("/cvws/{camera_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    camera_id: str,
):
    token = websocket.query_params.get("token")
    payload = _validate_token(token) if token else None
    if payload is None:
        logger.warning("WS connection rejected for camera %s (token present: %s)", camera_id, bool(token))
        await websocket.close(code=4001, reason="Invalid or expired token")
        return

    await websocket.accept()
    logger.info("🟢 WEBSOCKET CONNECTED for camera %s", camera_id)
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
        logger.info("🔴 WEBSOCKET DISCONNECTED for camera %s", camera_id)
    except Exception as e:
        logger.error("WebSocket error for %s: %s", camera_id, e)
    finally:
        try:
            await websocket.close()
        except Exception:
            pass


@app.get("/cvws/{camera_id}")
async def cvws_http_fallback(camera_id: str):
    """
    HTTP GET endpoint for /cvws/{camera_id}.
    Returns the latest JPEG frame for the camera.
    """
    frame = frame_store.latest_bytes(camera_id, annotated=True)
    if frame:
        logger.debug("HTTP GET frame served for camera %s (%d bytes)", camera_id, len(frame))
        return Response(content=frame, media_type="image/jpeg")
    return Response(content=b"", media_type="image/jpeg", status_code=204)



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
