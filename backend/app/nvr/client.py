import logging
from datetime import datetime
from urllib.parse import urlencode, urlparse, parse_qs

import httpx

logger = logging.getLogger(__name__)


class DahuaNvrClient:
    def __init__(self, host: str, username: str, password: str, port: int = 80):
        self.base_url = f"http://{host}:{port}"
        self.rtsp_base = f"rtsp://{username}:{password}@{host}:554"
        self.auth = httpx.DigestAuth(username=username, password=password)
        self._client = httpx.AsyncClient(auth=self.auth, timeout=10.0)

    async def close(self):
        await self._client.aclose()

    async def _get(self, path: str, params: dict | None = None) -> httpx.Response:
        url = f"{self.base_url}{path}"
        resp = await self._client.get(url, params=params)
        resp.raise_for_status()
        return resp

    async def get_snapshot(self, channel: int) -> bytes:
        resp = await self._get("/cgi-bin/snapshot.cgi", {"channel": channel})
        content = resp.content
        if not content.startswith(b"\xff\xd8"):
            # If it's not a valid JPEG, it's likely a JSON/text error (e.g. CGI not supported)
            error_msg = content.decode('utf-8', errors='ignore').strip()
            raise ValueError(f"NVR returned non-JPEG snapshot data: {error_msg}")
        return content

    async def search_recordings(
        self, channel: int, start_time: datetime, end_time: datetime, count: int = 100
    ) -> list[dict]:
        start = start_time.strftime("%Y-%m-%d %H:%M:%S")
        end = end_time.strftime("%Y-%m-%d %H:%M:%S")

        # Step 1: create session
        resp = await self._get("/cgi-bin/mediaFileFind.cgi", {"action": "create"})
        session_id = None
        for line in resp.text.split("\n"):
            if "sessionID" in line:
                session_id = line.split("=", 1)[1].strip()
                break
        if not session_id:
            logger.error("Failed to create mediaFileFind session: %s", resp.text)
            return []

        try:
            # Step 2: start find
            await self._get("/cgi-bin/mediaFileFind.cgi", {
                "action": "startFind",
                "sessionID": session_id,
                "channel": channel,
                "startTime": start,
                "endTime": end,
                "subtype": "0",
                "types": "0,1,2,3",
            })

            # Step 3: do find
            resp = await self._get("/cgi-bin/mediaFileFind.cgi", {
                "action": "doFind",
                "sessionID": session_id,
                "count": count,
            })

            results = []
            current = {}
            for line in resp.text.strip().split("\n"):
                line = line.strip()
                if not line or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                parts = key.split(".")
                if len(parts) >= 4 and parts[0] == "item":
                    idx = parts[1]
                    field = parts[-1]
                    if field == "fileName":
                        if current:
                            results.append(current)
                        current = {"index": idx, "fileName": value}
                    elif field in ("fileLength", "startTime", "endTime", "channel", "type", "subtype"):
                        current[field] = value
            if current:
                results.append(current)
            return results
        finally:
            # Step 4: destroy
            try:
                await self._get("/cgi-bin/mediaFileFind.cgi", {
                    "action": "destroy",
                    "sessionID": session_id,
                })
            except Exception as e:
                logger.warning("Failed to destroy mediaFileFind session: %s", e)

    def get_playback_url(self, channel: int, at: datetime) -> str:
        return (
            f"{self.rtsp_base}/cam/playback"
            f"?channel={channel}&starttime={at.strftime('%Y_%m_%d_%H_%M_%S')}"
        )

    async def get_storage_info(self) -> list[dict]:
        resp = await self._get("/cgi-bin/configManager.cgi", {
            "action": "getConfig",
            "name": "StorageInfo",
        })
        disks = []
        current = {}
        for line in resp.text.strip().split("\n"):
            line = line.strip()
            if not line or "=" not in line:
                continue
            key, _, value = line.partition("=")
            parts = key.split(".")
            if len(parts) >= 3 and parts[0] == "table" and parts[1] == "StorageInfo":
                idx = parts[2]
                field = ".".join(parts[3:]) if len(parts) > 3 else ""
                if field == "Name" and current:
                    disks.append(current)
                    current = {"index": idx, "Name": value}
                elif field == "Name":
                    current = {"index": idx, "Name": value}
                elif field:
                    current[field] = value
        if current:
            disks.append(current)
        return disks

    async def get_channel_status(self) -> list[dict]:
        resp = await self._get("/cgi-bin/configManager.cgi", {
            "action": "getConfig",
            "name": "ChannelTitle",
        })
        channels = []
        current = {}
        for line in resp.text.strip().split("\n"):
            line = line.strip()
            if not line or "=" not in line:
                continue
            key, _, value = line.partition("=")
            parts = key.split(".")
            if len(parts) >= 3 and parts[0] == "table" and parts[1] == "ChannelTitle":
                idx = parts[2]
                field = parts[3] if len(parts) > 3 else ""
                if field == "Name" and current:
                    channels.append(current)
                    current = {"index": idx, "Name": value, "Online": False}
                elif field == "Name":
                    current = {"index": idx, "Name": value, "Online": False}
                elif field in ("Online",):
                    current["Online"] = value.strip().lower() in ("true", "1")
        if current:
            channels.append(current)
        return channels

    async def get_system_time(self) -> str | None:
        resp = await self._get("/cgi-bin/global.cgi", {"action": "getCurrentTime"})
        for line in resp.text.strip().split("\n"):
            if "=" in line:
                return line.split("=", 1)[1].strip()
        return None


_nvr_client: DahuaNvrClient | None = None


def get_nvr_client() -> DahuaNvrClient | None:
    return _nvr_client


async def init_nvr_client(host: str, username: str, password: str):
    global _nvr_client
    if _nvr_client:
        await _nvr_client.close()
    _nvr_client = DahuaNvrClient(host, username, password)


async def close_nvr_client():
    global _nvr_client
    if _nvr_client:
        await _nvr_client.close()
        _nvr_client = None
