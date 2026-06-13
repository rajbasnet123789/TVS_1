import json
import logging
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self):
        self._connections: dict[str, set[WebSocket]] = {}
        self._user_connections: dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, channel: str = "global"):
        await websocket.accept()
        if channel not in self._connections:
            self._connections[channel] = set()
        self._connections[channel].add(websocket)
        logger.info(f"WebSocket connected to channel '{channel}': {id(websocket)}")

    def disconnect(self, websocket: WebSocket, channel: str = "global"):
        if channel in self._connections:
            self._connections[channel].discard(websocket)
            if not self._connections[channel]:
                del self._connections[channel]
        logger.info(f"WebSocket disconnected from channel '{channel}': {id(websocket)}")

    async def broadcast(self, channel: str, message: dict[str, Any]):
        if channel not in self._connections:
            return
        data = json.dumps(message)
        stale = set()
        for ws in self._connections[channel]:
            try:
                await ws.send_text(data)
            except Exception:
                stale.add(ws)
        for ws in stale:
            self._connections[channel].discard(ws)

    async def broadcast_camera_status(self, camera_id: str, status: str):
        await self.broadcast("camera_status", {
            "type": "camera_status",
            "camera_id": camera_id,
            "status": status,
        })

    async def broadcast_detection(self, detection: dict):
        await self.broadcast("detections", {
            "type": "detection",
            **detection,
        })

    async def broadcast_alert(self, alert: dict):
        await self.broadcast("alerts", {
            "type": "alert",
            **alert,
        })


manager = ConnectionManager()
