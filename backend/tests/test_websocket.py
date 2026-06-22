import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi import WebSocket
from app.websocket.manager import ConnectionManager


@pytest.mark.asyncio
async def test_connection_manager_tracking():
    manager = ConnectionManager()
    
    # Mock websockets
    ws1 = MagicMock(spec=WebSocket)
    ws1.accept = AsyncMock()
    ws1.send_text = AsyncMock()
    
    ws2 = MagicMock(spec=WebSocket)
    ws2.accept = AsyncMock()
    ws2.send_text = AsyncMock()

    # Test connect
    await manager.connect(ws1, "global")
    assert ws1 in manager._connections["global"]
    assert "global" in manager._ws_channels[ws1]

    # Test connect_channels
    await manager.connect_channels(ws2, ["channel1", "channel2"])
    assert ws2 in manager._connections["channel1"]
    assert ws2 in manager._connections["channel2"]
    assert "channel1" in manager._ws_channels[ws2]
    assert "channel2" in manager._ws_channels[ws2]

    # Test broadcast
    await manager.broadcast("channel1", {"test": "data"})
    ws2.send_text.assert_called_once()

    # Test disconnect_all
    manager.disconnect_all(ws2)
    assert "channel1" not in manager._connections
    assert "channel2" not in manager._connections
    assert ws2 not in manager._ws_channels

    # Test disconnect
    manager.disconnect(ws1, "global")
    assert "global" not in manager._connections
    assert ws1 not in manager._ws_channels
