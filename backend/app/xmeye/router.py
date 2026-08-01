"""
XMEye / DVRIP API router.

Endpoints:
  POST /xmeye/scan     — proxy to cv-engine which does UDP broadcast on host network
  POST /xmeye/connect  — DVRIP TCP login to validate credentials and list channels
  POST /xmeye/add      — Add selected NVR channels as cameras in the database

Why proxy /scan to cv-engine?
  UDP broadcasts (255.255.255.255:34568) do NOT cross Docker bridge NAT.
  The backend runs in Docker bridge mode and cannot reach the physical LAN
  via broadcast. cv-engine runs with network_mode:host and has full LAN access.
"""
import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_farm_id, require_permission
from app.auth.models import User
from app.cameras.schemas import CameraCreate, CameraOut
from app.cameras.service import create_camera
from app.database import get_db
from app.xmeye.client import (
    DVRIPAuthError,
    build_all_rtsp_urls,
    dvrip_login,
)
from app.xmeye.schemas import (
    XMEyeAddChannelsRequest,
    XMEyeChannelInfo,
    XMEyeConnectRequest,
    XMEyeConnectResponse,
    XMEyeDiscoveredDevice,
    XMEyeScanResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/xmeye", tags=["xmeye"])

# cv-engine runs with network_mode:host — reachable from backend via
# host.docker.internal (Docker bridge gateway) on port 8700.
_CV_ENGINE_URL = "http://host.docker.internal:8700"


@router.post("/scan", response_model=XMEyeScanResponse)
async def scan_xmeye_devices(
    user: User = Depends(require_permission("cameras:scan")),
):
    """
    Discover XMEye/DVRIP cameras on the LAN.

    Proxies the request to cv-engine (network_mode:host) which performs the
    UDP broadcast. The backend cannot do this directly because Docker bridge
    network blocks UDP broadcasts from reaching the physical LAN.
    """
    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            resp = await client.post(f"{_CV_ENGINE_URL}/xmeye-scan", params={"timeout": 5.0})
            resp.raise_for_status()
            data = resp.json()
    except httpx.ConnectError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="cv-engine is not reachable. Make sure it is running and healthy.",
        )
    except Exception as exc:
        logger.error("XMEye scan proxy error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"XMEye LAN scan failed: {exc}",
        )

    raw_devices = data.get("devices", [])
    devices = [
        XMEyeDiscoveredDevice(
            ip=d["ip"],
            tcp_port=d.get("tcp_port", 34567),
            http_port=d.get("http_port", 80),
            device_name=d.get("device_name") or f"XMEye @ {d['ip']}",
            device_type=d.get("device_type", ""),
            serial_no=d.get("serial_no", ""),
            mac=d.get("mac", ""),
            channel_count=d.get("channel_count", 1),
            software_version=d.get("software_version", ""),
            build_date=d.get("build_date", ""),
        )
        for d in raw_devices
    ]
    return XMEyeScanResponse(devices=devices, count=len(devices))


@router.post("/connect", response_model=XMEyeConnectResponse)
async def connect_xmeye_device(
    req: XMEyeConnectRequest,
    user: User = Depends(require_permission("cameras:write")),
):
    """
    Validate DVRIP credentials and enumerate channels for a specific XMEye device.

    Performs a TCP DVRIP login to confirm credentials are correct, then builds
    the RTSP URLs for all channels in both supported URL formats (A & B).
    The user can then choose which channels to add as cameras.
    """
    try:
        resp = await dvrip_login(
            ip=req.ip,
            port=req.port,
            username=req.username,
            password=req.password,
        )
    except DVRIPAuthError as exc:
        return XMEyeConnectResponse(
            success=False,
            error=str(exc),
        )
    except (OSError, TimeoutError, ConnectionError) as exc:
        return XMEyeConnectResponse(
            success=False,
            error=f"Cannot reach device at {req.ip}:{req.port} — {exc}",
        )
    except Exception as exc:
        logger.error("XMEye connect unexpected error: %s", exc)
        return XMEyeConnectResponse(
            success=False,
            error=f"Unexpected error: {exc}",
        )

    # Determine channel count — use override, then DVRIP response, then 1
    channel_count = (
        req.channel_count
        or resp.get("ChannelNum")
        or resp.get("ExtraChannel")
        or 1
    )
    channel_count = max(1, int(channel_count))

    session_id = resp.get("SessionID", "")
    device_type = resp.get("DeviceType") or resp.get("DevType") or "Unknown"

    # Build channel list with all RTSP URL variants
    channels: list[XMEyeChannelInfo] = []
    for ch in range(1, channel_count + 1):
        urls = build_all_rtsp_urls(
            host=req.ip,
            username=req.username,
            password=req.password,
            channel=ch,
            rtsp_port=req.rtsp_port,
        )
        channels.append(
            XMEyeChannelInfo(
                channel=ch,
                name=f"Channel {ch}",
                rtsp_url_main=urls["main_stream_format_a"],
                rtsp_url_sub=urls["sub_stream_format_a"],
                rtsp_url_main_b=urls["main_stream_format_b"],
                rtsp_url_sub_b=urls["sub_stream_format_b"],
            )
        )

    return XMEyeConnectResponse(
        success=True,
        session_id=str(session_id),
        device_type=device_type,
        channels=channels,
    )


@router.post("/add", response_model=list[CameraOut])
async def add_xmeye_channels(
    req: XMEyeAddChannelsRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("cameras:write")),
    farm_id: str | None = Depends(get_farm_id),
):
    """
    Add selected XMEye NVR channels as cameras in the database.

    For each selected channel, builds the RTSP URL and creates a Camera record
    that cv-engine will pick up automatically within 10 seconds.
    """
    if not farm_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Farm ID is required. Set X-Farm-ID header or select a farm.",
        )

    if not req.channels:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No channels selected.",
        )

    created: list[CameraOut] = []
    errors: list[str] = []

    for ch in sorted(set(req.channels)):
        from app.xmeye.client import build_xmeye_rtsp_url

        rtsp_url = build_xmeye_rtsp_url(
            host=req.ip,
            username=req.username,
            password=req.password,
            channel=ch,
            substream=req.use_substream,
            rtsp_port=req.rtsp_port,
            format=req.rtsp_format,
        )

        cam_create = CameraCreate(
            name=f"NVR {req.ip} — Ch{ch}",
            rtsp_url=rtsp_url,
            location=req.location,
            zone=req.zone,
            fps_target=req.fps_target,
            username=req.username,
            password=req.password,
        )

        try:
            cam = await create_camera(db, cam_create, farm_id=farm_id)
            created.append(CameraOut.model_validate(cam))
        except Exception as exc:
            logger.error("XMEye: failed to create camera for channel %d: %s", ch, exc)
            errors.append(f"Channel {ch}: {exc}")

    if errors and not created:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"All channels failed: {'; '.join(errors)}",
        )

    return created
