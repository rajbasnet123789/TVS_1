"""Tests for the Frigate integration module (config_manager, client, subscriber)."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.frigate.schemas import FrigateCameraConfig, FrigateEvent
from app.frigate.config_manager import build_camera_config, build_full_config, generate_camera_yaml


class TestFrigateSchemas:
    def test_frigate_camera_config_defaults(self):
        cfg = FrigateCameraConfig(name="test_cam", rtsp_url="rtsp://192.168.1.100:554/stream1")
        assert cfg.enabled is True
        assert cfg.objects_to_track == ["bird"]
        assert cfg.record_days == 7
        assert cfg.detect_enabled is True

    def test_frigate_camera_config_with_credentials(self):
        cfg = FrigateCameraConfig(
            name="test_cam",
            rtsp_url="rtsp://192.168.1.100:554/stream1",
            username="admin",
            password="secret",
        )
        assert cfg.username == "admin"
        assert cfg.password == "secret"

    def test_frigate_event_model(self):
        event = FrigateEvent(type="new", after={"label": "bird", "id": "abc123"})
        assert event.type == "new"
        assert event.after["label"] == "bird"


class TestConfigManager:
    def test_build_camera_config_basic(self):
        cfg = FrigateCameraConfig(name="cam1", rtsp_url="rtsp://192.168.1.10:554/live")
        result = build_camera_config(cfg)
        assert "ffmpeg" in result
        assert result["ffmpeg"]["inputs"][0]["path"] == "rtsp://192.168.1.10:554/live"
        assert result["detect"]["fps"] == 5
        assert result["objects"]["track"] == ["bird"]
        assert result["record"]["retain"]["days"] == 7

    def test_build_camera_config_with_credentials_injects_password(self):
        cfg = FrigateCameraConfig(
            name="cam1",
            rtsp_url="rtsp://192.168.1.10:554/live",
            username="admin",
            password="hunter2",
        )
        result = build_camera_config(cfg)
        path = result["ffmpeg"]["inputs"][0]["path"]
        assert "admin:hunter2@" in path

    def test_build_camera_config_no_credentials_leaves_url(self):
        cfg = FrigateCameraConfig(name="cam1", rtsp_url="rtsp://admin:hunter2@192.168.1.10:554/live")
        result = build_camera_config(cfg)
        path = result["ffmpeg"]["inputs"][0]["path"]
        # No username/password on the config object, so URL stays as-is
        assert path == "rtsp://admin:hunter2@192.168.1.10:554/live"

    def test_build_full_config_empty(self):
        result = build_full_config([])
        assert "cameras" in result
        assert result["cameras"] == {}
        assert result["mqtt"]["host"] == "mosquitto"

    def test_build_full_config_with_cameras(self):
        cam_cfg = FrigateCameraConfig(name="cam1", rtsp_url="rtsp://10.0.0.1:554/stream")
        cfg = build_camera_config(cam_cfg)
        cfg["name"] = cam_cfg.name
        result = build_full_config([cfg])
        assert "cam1" in result["cameras"]
        assert result["cameras"]["cam1"]["detect"]["fps"] == 5

    def test_generate_camera_yaml(self):
        cfg = FrigateCameraConfig(name="cam1", rtsp_url="rtsp://10.0.0.1:554/stream")
        yaml_str = generate_camera_yaml(cfg)
        assert "cam1:" in yaml_str
        assert "rtsp://10.0.0.1:554/stream" in yaml_str
        assert "bird" in yaml_str


class TestClient:
    @patch("app.frigate.client.get_client")
    @pytest.mark.asyncio
    async def test_get_frigate_stats(self, mock_get_client):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"cameras": {"cam1": {"detection_enabled": True}}}
        mock_http = AsyncMock()
        mock_http.get.return_value = mock_resp
        mock_get_client.return_value = mock_http

        from app.frigate.client import get_frigate_stats
        stats = await get_frigate_stats()
        assert stats["cameras"]["cam1"]["detection_enabled"] is True
        mock_http.get.assert_called_once_with("/api/stats")

    @patch("app.frigate.client.get_client")
    @pytest.mark.asyncio
    async def test_get_camera_events(self, mock_get_client):
        mock_resp = MagicMock()
        mock_resp.json.return_value = [{"id": "evt1", "label": "bird"}]
        mock_http = AsyncMock()
        mock_http.get.return_value = mock_resp
        mock_get_client.return_value = mock_http

        from app.frigate.client import get_camera_events
        events = await get_camera_events("cam1")
        assert len(events) == 1
        assert events[0]["id"] == "evt1"

    @patch("app.frigate.client.get_client")
    @pytest.mark.asyncio
    async def test_get_snapshot_found(self, mock_get_client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b"fake_jpeg_bytes"
        mock_http = AsyncMock()
        mock_http.get.return_value = mock_resp
        mock_get_client.return_value = mock_http

        from app.frigate.client import get_snapshot
        data = await get_snapshot("cam1")
        assert data == b"fake_jpeg_bytes"

    @patch("app.frigate.client.get_client")
    @pytest.mark.asyncio
    async def test_get_snapshot_not_found(self, mock_get_client):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_http = AsyncMock()
        mock_http.get.return_value = mock_resp
        mock_get_client.return_value = mock_http

        from app.frigate.client import get_snapshot
        data = await get_snapshot("cam1")
        assert data is None

    @patch("app.frigate.client.get_client")
    @pytest.mark.asyncio
    async def test_get_camera_status(self, mock_get_client):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "cameras": {
                "cam1": {"detection_enabled": True, "detection_fps": 5.0}
            }
        }
        mock_http = AsyncMock()
        mock_http.get.return_value = mock_resp
        mock_get_client.return_value = mock_http

        from app.frigate.client import get_camera_status
        status = await get_camera_status("cam1")
        assert status is not None
        assert status["detection_fps"] == 5.0


class TestSubscriber:
    @pytest.mark.asyncio
    async def test_handle_message_bird_event(self):
        from app.frigate.subscriber import FrigateSubscriber
        sub = FrigateSubscriber()

        # Mock MQTT message payload
        payload = (
            b'{"type":"new","after":{"id":"evt1","camera":"cam1","label":"bird",'
            b'"top_score":0.85,"false_positive":false,"has_snapshot":true,'
            b'"start_time":1234567890.0,"bbox":[100,200,300,400]}}'
        )

        with patch.object(sub, "_handle_detection_event", new=AsyncMock()) as mock_handle:
            await sub._handle_message("frigate/cam1/events/new", payload)
            mock_handle.assert_awaited_once()
            args, _ = mock_handle.call_args
            assert args[0] == "cam1"

    @pytest.mark.asyncio
    async def test_handle_message_non_bird_ignored(self):
        from app.frigate.subscriber import FrigateSubscriber
        sub = FrigateSubscriber()

        payload = (
            b'{"type":"new","after":{"id":"evt2","label":"dog",'
            b'"top_score":0.9,"false_positive":false,"has_snapshot":true}}'
        )

        with patch.object(sub, "_handle_detection_event", new=AsyncMock()) as mock_handle:
            await sub._handle_message("frigate/cam1/events/new", payload)
            # Early label filter at line 78 returns before _handle_detection_event
            mock_handle.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_handle_message_bad_json(self):
        from app.frigate.subscriber import FrigateSubscriber
        sub = FrigateSubscriber()
        with patch.object(sub, "_handle_detection_event", new=AsyncMock()) as mock_handle:
            await sub._handle_message("frigate/cam1/events/new", b"not json")
            mock_handle.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_resolve_farm_id(self):
        from app.frigate.subscriber import FrigateSubscriber
        sub = FrigateSubscriber()
        # No DB in unit test — should return None gracefully
        farm_id = await sub._resolve_farm_id("nonexistent_camera")
        assert farm_id is None

    @pytest.mark.asyncio
    async def test_health_worker_timeout(self):
        from app.frigate.subscriber import FrigateSubscriber
        sub = FrigateSubscriber()
        sub._running = False  # stop immediately
        # Should not raise — TimeoutError is caught internally
        await sub._health_worker()
