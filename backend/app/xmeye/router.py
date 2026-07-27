"""
XMEye / DVRIP API router.

Endpoints:
  POST /xmeye/scan     — UDP broadcast to discover XMEye devices on the LAN
  POST /xmeye/connect  — DVRIP TCP login to validate credentials and list channels
  POST /xmeye/add      — Add selected NVR channels as cameras in the database
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_farm_id, require_permission
from app.auth.models import User
from app.cameras.models import Camera
from app.cameras.schemas import CameraOut
from app.cameras.service import create_camera
from app.cameras.schemas import CameraCreate
from app.database import get_db
from app.xmeye.client import (
    DVRIPAuthError,
    build_all_rtsp_urls,
    dvrip_login,
)
from app.xmeye.discovery import discover_xmeye_devices
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


@router.post("/scan", response_model=XMEyeScanResponse)
async def scan_xmeye_devices(
    user: User = Depends(require_permission("cameras:scan")),
):
    """
    Broadcast-scan the local LAN for XMEye/DVRIP cameras and NVRs.

    Sends a UDP broadcast to 255.255.255.255:34568 and collects JSON responses
    from Xiongmai-based devices (XMEye, Dahua OEM, etc.).

    Returns a list of discovered devices with their IP, channel count, and device info.
    No credentials are required for discovery — this is a read-only LAN broadcast.
    """
    try:
        raw_devices = await discover_xmeye_devices(timeout=5.0)
    except Exception as exc:
        logger.error("XMEye LAN scan failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"XMEye LAN scan failed: {exc}",
        )

    devices = [
        XMEyeDiscoveredDevice(
            ip=d.ip,
            tcp_port=d.tcp_port,
            http_port=d.http_port,
            device_name=d.device_name or f"XMEye device @ {d.ip}",
            device_type=d.device_type,
            serial_no=d.serial_no,
            mac=d.mac,
            channel_count=d.channel_count,
            software_version=d.software_version,
            build_date=d.build_date,
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
