import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


_client: httpx.AsyncClient | None = None


async def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(base_url=settings.frigate_api_url, timeout=30)
    return _client


async def close_client():
    global _client
    if _client:
        await _client.aclose()
        _client = None


async def get_frigate_stats() -> dict:
    client = await get_client()
    resp = await client.get("/api/stats")
    resp.raise_for_status()
    return resp.json()


async def get_frigate_config() -> dict:
    client = await get_client()
    resp = await client.get("/api/config")
    resp.raise_for_status()
    return resp.json()


async def save_frigate_config(config: dict):
    client = await get_client()
    resp = await client.put("/api/config/save", json=config)
    resp.raise_for_status()
    logger.info("Frigate config saved via API")


async def get_recordings(camera_name: str, before: int | None = None, after: int | None = None, limit: int = 100) -> list[dict]:
    client = await get_client()
    params = {"limit": limit, "camera": camera_name}
    if before: params["before"] = before
    if after: params["after"] = after
    resp = await client.get("/api/recordings", params=params)
    resp.raise_for_status()
    data = resp.json()
    return data.get("recordings", [])


async def get_snapshot(camera_name: str, timestamp: float | None = None, bbox: bool = True) -> bytes | None:
    client = await get_client()
    params = {"bbox": str(bbox).lower()}
    if timestamp:
        params["ts"] = str(timestamp)
    resp = await client.get(f"/api/{camera_name}/snapshot.jpg", params=params, timeout=10)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.content


async def get_event_snapshot(event_id: str) -> bytes | None:
    client = await get_client()
    resp = await client.get(f"/api/events/{event_id}/snapshot.jpg", timeout=10)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.content


async def get_camera_events(camera_name: str, limit: int = 50, labels: str | None = "bird") -> list[dict]:
    client = await get_client()
    params: dict = {"camera": camera_name, "limit": limit}
    if labels:
        params["labels"] = labels
    resp = await client.get("/api/events", params=params)
    resp.raise_for_status()
    return resp.json()


async def reload_config():
    client = await get_client()
    resp = await client.post("/api/config/reload")
    resp.raise_for_status()
    logger.info("Frigate config reloaded")


async def get_camera_status(camera_name: str) -> dict | None:
    try:
        stats = await get_frigate_stats()
        cameras = stats.get("cameras", {})
        return cameras.get(camera_name)
    except Exception as e:
        logger.warning(f"Failed to get camera status for {camera_name}: {e}")
        return None
