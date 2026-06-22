from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.auth.service import decode_token
from app.websocket.manager import manager

router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: str | None = None):
    token = token or websocket.cookies.get("access_token")
    if not token:
        await websocket.close(code=4001)
        return

    payload = decode_token(token)
    if payload is None or payload.get("type") != "access":
        await websocket.close(code=4001)
        return

    role_name = payload.get("role", "viewer")
    if role_name == "super_admin":
        farm_id = websocket.query_params.get("farm_id") or payload.get("farm_id", None)
    else:
        farm_id = payload.get("farm_id", None)

    if farm_id:
        channels = [
            f"farm_{farm_id}/detections",
            f"farm_{farm_id}/alerts",
            f"farm_{farm_id}/camera_status",
        ]
        await manager.connect(websocket, channel=f"farm_{farm_id}")
    else:
        channels = ["detections", "alerts", "camera_status", "health"]
        await manager.connect(websocket, channel="global")

    await manager.connect_channels(websocket, channels)

    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        manager.disconnect_all(websocket)
