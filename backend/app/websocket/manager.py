import json
import logging
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self):
        self._connections: dict[str, set[WebSocket]] = {}
        self._ws_channels: dict[WebSocket, set[str]] = {}

    async def connect(self, websocket: WebSocket, channel: str = "global"):
        await websocket.accept()
        if channel not in self._connections:
            self._connections[channel] = set()
        self._connections[channel].add(websocket)
        if websocket not in self._ws_channels:
            self._ws_channels[websocket] = set()
        self._ws_channels[websocket].add(channel)
        logger.info(f"WebSocket connected to channel '{channel}': {id(websocket)}")

    def disconnect(self, websocket: WebSocket, channel: str = "global"):
        if channel in self._connections:
            self._connections[channel].discard(websocket)
            if not self._connections[channel]:
                del self._connections[channel]
        if websocket in self._ws_channels:
            self._ws_channels[websocket].discard(channel)
            if not self._ws_channels[websocket]:
                del self._ws_channels[websocket]
        logger.info(f"WebSocket disconnected from channel '{channel}': {id(websocket)}")

    def disconnect_all(self, websocket: WebSocket):
        if websocket in self._ws_channels:
            channels = list(self._ws_channels[websocket])
            for ch in channels:
                self.disconnect(websocket, ch)
        else:
            # Fallback: check all connections
            for ch in list(self._connections.keys()):
                if websocket in self._connections[ch]:
                    self.disconnect(websocket, ch)
        logger.info(f"WebSocket fully disconnected and cleaned up: {id(websocket)}")

    async def connect_channels(self, websocket: WebSocket, channels: list[str]):
        for ch in channels:
            if ch not in self._connections:
                self._connections[ch] = set()
            self._connections[ch].add(websocket)
            if websocket not in self._ws_channels:
                self._ws_channels[websocket] = set()
            self._ws_channels[websocket].add(ch)

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
            self.disconnect(ws, channel)


manager = ConnectionManager()
