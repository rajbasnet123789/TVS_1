from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.auth.service import decode_token
from app.websocket.manager import manager

router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: str | None = None):
    if not token:
        await websocket.close(code=4001)
        return

    payload = decode_token(token)
    if payload is None or payload.get("type") != "access":
        await websocket.close(code=4001)
        return

    await manager.connect(websocket, channel="global")
    channels = ["global", "detections", "alerts", "camera_status"]
    for ch in channels:
        if ch not in manager._connections:
            manager._connections[ch] = set()
        manager._connections[ch].add(websocket)

    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        for ch in channels:
            manager.disconnect(websocket, ch)
