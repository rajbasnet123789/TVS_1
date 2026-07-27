import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import require_permission, get_farm_id
from app.auth.models import User
from app.cameras.models import Camera
from app.database import get_db
from app.rate_limit import limiter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/nvr", tags=["nvr"])


class DiscoveredChannel(BaseModel):
    channel: int
    name: str
    online: bool
    rtsp_url: str


class ConnectNvrRequest(BaseModel):
    device_name: str | None = None
    group: str | None = None
    login_type: str = "IP Address"
    ip: str
    port: int = 34567
    username: str | None = "admin"
    password: str | None = ""
    protocol: str = "General"


class RegisterCamerasRequest(BaseModel):
    cameras: list[DiscoveredChannel]
    farm_id: str
    username: str | None = None
    password: str | None = None


async def _resolve_camera(camera_id: str, db: AsyncSession, farm_id: str | None = None, is_super_admin: bool = False) -> Camera:
    from uuid import UUID
    try:
        UUID(camera_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid camera ID")
    result = await db.execute(select(Camera).where(Camera.id == camera_id))
    camera = result.scalar_one_or_none()
    if not camera:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Camera not found")
    if farm_id and str(camera.farm_id) != farm_id and not is_super_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    return camera


@router.post("/connect")
async def connect_nvr(
    data: ConnectNvrRequest,
    user: User = Depends(require_permission("cameras:scan")),
):
    ip = data.ip.strip()
    if not ip:
        raise HTTPException(status_code=400, detail="IP address or domain is required")

    port = data.port or 34567
    username = data.username or "admin"
    password = data.password or ""
    protocol = data.protocol or "General"
    auth_str = f"{username}:{password}@" if username else ""

    channels: list[DiscoveredChannel] = []

    # 1. Try Dahua / CGI protocol if Dahua selected or port is default
    if protocol.lower() in ("dahua", "general"):
        from app.nvr.client import DahuaNvrClient
        client = DahuaNvrClient(host=ip, username=username, password=password, port=port if port in (80, 8080) else 80)
        try:
            ch_status = await client.get_channel_status()
            for ch in ch_status:
                idx = int(ch.get("index", 0))
                name = ch.get("Name", f"Channel {idx}")
                online = ch.get("Online", True)
                rtsp_url = f"rtsp://{auth_str}{ip}:554/cam/realmonitor?channel={idx}&subtype=0"
                channels.append(DiscoveredChannel(channel=idx, name=name, online=online, rtsp_url=rtsp_url))
            await client.close()
        except Exception as e:
            logger.debug("Dahua CGI probe attempt skipped: %s", e)
            await client.close()

    # 2. If no channels returned from CGI probe, build default channel streams based on Protocol
    if not channels:
        num_channels = 16  # standard NVR 16 channels layout
        if protocol.lower() == "hikvision":
            for idx in range(1, num_channels + 1):
                rtsp_url = f"rtsp://{auth_str}{ip}:554/Streaming/Channels/{idx}01"
                channels.append(DiscoveredChannel(channel=idx, name=f"{data.device_name or ip} - Ch {idx}", online=True, rtsp_url=rtsp_url))
        elif protocol.lower() == "uniview":
            for idx in range(1, num_channels + 1):
                rtsp_url = f"rtsp://{auth_str}{ip}:554/unicast/c{idx}/s0/live"
                channels.append(DiscoveredChannel(channel=idx, name=f"{data.device_name or ip} - Ch {idx}", online=True, rtsp_url=rtsp_url))
        elif protocol.lower() == "onvif":
            for idx in range(1, num_channels + 1):
                rtsp_url = f"rtsp://{auth_str}{ip}:554/onvif{idx}"
                channels.append(DiscoveredChannel(channel=idx, name=f"ONVIF Ch {idx} ({ip})", online=True, rtsp_url=rtsp_url))
        else:
            # General / Default NVR RTSP pattern (Dahua/General RTSP)
            rtsp_base_port = 554 if port in (34567, 80, 8080) else port
            for idx in range(1, num_channels + 1):
                rtsp_url = f"rtsp://{auth_str}{ip}:{rtsp_base_port}/cam/realmonitor?channel={idx}&subtype=0"
                channels.append(DiscoveredChannel(channel=idx, name=f"{data.device_name or ip} - Ch {idx}", online=True, rtsp_url=rtsp_url))

    return {
        "device_name": data.device_name or ip,
        "ip": ip,
        "port": port,
        "login_type": data.login_type,
        "protocol": protocol,
        "cameras": channels,
    }


@router.get("/discover")
async def discover_nvr_cameras(
    user: User = Depends(require_permission("cameras:scan")),
):
    from app.nvr.client import get_nvr_client
    client = get_nvr_client()
    if client:
        try:
            channels = await client.get_channel_status()
            discovered = []
            for ch in channels:
                idx = int(ch.get("index", 0))
                name = ch.get("name", f"Channel {idx}")
                online = ch.get("Online", False)
                rtsp_url = f"{client.rtsp_base}/cam/realmonitor?channel={idx}&subtype=0"
                discovered.append(DiscoveredChannel(
                    channel=idx, name=name, online=online, rtsp_url=rtsp_url
                ))
            return {"cameras": discovered, "nvr_host": client.base_url}
        except Exception as e:
            logger.warning("Configured NVR client discovery failed, falling back to local network scan: %s", e)

    # Fallback to local network ONVIF WS-Discovery scan
    from app.cameras.onvif import discover_onvif_devices
    onvif_devices = await discover_onvif_devices(timeout=6)
    discovered = []
    for idx, d in enumerate(onvif_devices, start=1):
        ip = d.get("ip", "")
        name = d.get("name", f"NVR / Camera {idx} ({ip})")
        rtsp_url = f"rtsp://{ip}:554/cam/realmonitor?channel=1&subtype=0" if ip else d.get("xaddrs", "")
        discovered.append(DiscoveredChannel(
            channel=idx, name=name, online=True, rtsp_url=rtsp_url
        ))

    return {"cameras": discovered, "nvr_host": "local_network"}


@router.post("/register")
async def register_nvr_cameras(
    data: RegisterCamerasRequest,
    user: User = Depends(require_permission("cameras:scan")),
    db: AsyncSession = Depends(get_db),
):
    from uuid import UUID
    try:
        farm_uuid = UUID(data.farm_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid farm ID")

    registered = []
    for cam in data.cameras:
        existing = await db.execute(
            select(Camera).where(Camera.rtsp_url == cam.rtsp_url, Camera.farm_id == farm_uuid)
        )
        if existing.scalar_one_or_none():
            continue

        from app.security import encrypt_camera_password
        camera = Camera(
            farm_id=farm_uuid,
            name=cam.name,
            rtsp_url=cam.rtsp_url,
            location=f"NVR Channel {cam.channel}",
            status="online" if cam.online else "offline",
            username=data.username,
            password_hash=encrypt_camera_password(data.password) if data.password else None,
            enabled=True,
        )
        db.add(camera)
        registered.append(cam.name)

    await db.commit()
    return {"registered": registered, "count": len(registered)}


@router.get("/snapshot/{camera_id}")
async def get_snapshot(
    camera_id: str,
    user: User = Depends(require_permission("nvr:read")),
    db: AsyncSession = Depends(get_db),
    farm_id: str | None = Depends(get_farm_id),
):
    camera = await _resolve_camera(camera_id, db, farm_id, user.role.name == "super_admin")
    if camera.snapshot_url:
        import httpx
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(camera.snapshot_url)
                if resp.status_code == 200:
                    from fastapi.responses import Response
                    return Response(content=resp.content, media_type="image/jpeg")
        except Exception as e:
            logger.warning(f"Failed to fetch snapshot: {e}")
    raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="No snapshot available")


@router.get("/channels")
async def get_channels(
    user: User = Depends(require_permission("nvr:read")),
    db: AsyncSession = Depends(get_db),
    farm_id: str | None = Depends(get_farm_id),
):
    query = select(Camera)
    if farm_id and user.role.name != "super_admin":
        query = query.where(Camera.farm_id == farm_id)
    result = await db.execute(query)
    cameras = result.scalars().all()
    channels = [
        {"index": str(i), "Name": cam.name, "Online": cam.status == "online"}
        for i, cam in enumerate(cameras)
    ]
    return {"channels": channels}


@router.get("/time")
async def get_time(
    _: User = Depends(require_permission("nvr:read")),
):
    from app.nvr.client import get_nvr_client
    client = get_nvr_client()
    if client:
        try:
            nvr_time = await client.get_system_time()
            if nvr_time:
                return {"nvr_time": nvr_time}
        except Exception as e:
            logger.warning("Failed to get NVR time: %s", e)
    return {"nvr_time": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")}
