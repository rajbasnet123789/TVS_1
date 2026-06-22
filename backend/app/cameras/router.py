import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_user, get_farm_id, require_permission
from app.auth.models import User
from app.cameras.models import Camera
from app.cameras.onvif import discover_onvif_devices
from app.cameras.schemas import AssignCoopRequest, CameraCreate, CameraOut, CameraUpdate, DiscoveredDevice, ScanStatus
from app.cameras.service import create_camera, delete_camera, get_camera, list_cameras, update_camera
from app.config import settings
from app.database import get_db
from app.rate_limit import limiter

def extract_ip_from_rtsp(rtsp_url: str) -> str | None:
    if not rtsp_url:
        return None
    url = rtsp_url if rtsp_url.startswith("rtsp://") else f"rtsp://{rtsp_url}"
    try:
        from urllib.parse import urlparse
        return urlparse(url).hostname
    except Exception:
        return None


router = APIRouter(prefix="/cameras", tags=["cameras"])

_scan_state: dict = {"scanning": False, "progress": None, "devices": [], "error": None, "task": None}


async def cancel_active_scan():
    global _scan_state
    task = _scan_state.get("task")
    if task and not task.done():
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


async def _run_scan():
    global _scan_state
    _scan_state = {"scanning": True, "progress": 0.0, "devices": [], "error": None}
    try:
        devices = await discover_onvif_devices(timeout=8)
        _scan_state["devices"] = [
            {
                "name": d["name"],
                "device_url": d["device_url"],
                "ip": d.get("ip", ""),
                "xaddrs": d["xaddrs"],
                "types": d["types"],
                "scopes": d["scopes"],
            }
            for d in devices
        ]
        _scan_state["progress"] = 1.0
    except Exception as e:
        _scan_state["error"] = str(e)
    finally:
        _scan_state["scanning"] = False


@router.get("", response_model=list[CameraOut])
async def get_cameras(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("cameras:read")),
    farm_id: str | None = Depends(get_farm_id),
):
    cameras = await list_cameras(db, farm_id=farm_id)
    result = []
    for cam in cameras:
        cam_out = CameraOut.model_validate(cam)
        cam_out.hls_url = f"/api/frigate/hls/{cam.name}/index.m3u8"
        result.append(cam_out)
    return result


@router.post("/scan", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("20/minute")
async def scan_network(
    request: Request,
    user: User = Depends(require_permission("cameras:scan")),
):
    global _scan_state
    
    # Cancel previous task if still running
    prev_task = _scan_state.get("task")
    if prev_task and not prev_task.done():
        prev_task.cancel()
        try:
            await prev_task
        except asyncio.CancelledError:
            pass
            
    task = asyncio.create_task(_run_scan())
    _scan_state["task"] = task
    return {"status": "started", "message": "ONVIF network scan started"}


@router.get("/scan/status", response_model=ScanStatus)
async def scan_status(
    user: User = Depends(require_permission("cameras:read")),
):
    return ScanStatus(
        scanning=_scan_state["scanning"],
        progress=_scan_state["progress"],
        devices_found=len(_scan_state["devices"]),
        error=_scan_state["error"],
    )


@router.get("/scan/results", response_model=list[DiscoveredDevice])
async def scan_results(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("cameras:read")),
):
    from app.cameras.service import list_cameras
    # Query all cameras across all farms (farm_id=None) to filter out already-connected IPs globally
    cameras = await list_cameras(db, farm_id=None)
    
    existing_ips = set()
    for cam in cameras:
        ip = extract_ip_from_rtsp(cam.rtsp_url)
        if ip:
            existing_ips.add(ip)
            
    filtered_devices = []
    for d in _scan_state["devices"]:
        if d.get("ip") not in existing_ips:
            filtered_devices.append(d)
            
    return filtered_devices


@router.get("/{camera_id}", response_model=CameraOut)
async def get_camera_detail(
    camera_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("cameras:read")),
    farm_id: str | None = Depends(get_farm_id),
):
    camera = await get_camera(db, camera_id)
    if not camera:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Camera not found")
    if farm_id and str(camera.farm_id) != farm_id and user.role.name != "super_admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    cam_out = CameraOut.model_validate(camera)
    cam_out.hls_url = f"/api/frigate/hls/{camera.name}/index.m3u8"
    return cam_out


@router.post("", response_model=CameraOut, status_code=status.HTTP_201_CREATED)
@limiter.limit("20/minute")
async def add_camera(
    data: CameraCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("cameras:write")),
    farm_id: str | None = Depends(get_farm_id),
):
    camera = await create_camera(db, data, farm_id=farm_id)
    cam_out = CameraOut.model_validate(camera)
    cam_out.hls_url = f"/api/frigate/hls/{camera.name}/index.m3u8"
    return cam_out


@router.put("/{camera_id}", response_model=CameraOut)
@limiter.limit("20/minute")
async def edit_camera(
    camera_id: str,
    request: Request,
    data: CameraUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("cameras:write")),
    farm_id: str | None = Depends(get_farm_id),
):
    camera = await get_camera(db, camera_id)
    if not camera:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Camera not found")
    if farm_id and str(camera.farm_id) != farm_id and user.role.name != "super_admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    camera = await update_camera(db, camera_id, data)
    if not camera:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Camera not found")

    cam_out = CameraOut.model_validate(camera)
    cam_out.hls_url = f"/api/frigate/hls/{camera.name}/index.m3u8"
    return cam_out


@router.put("/{camera_id}/assign-coop", response_model=CameraOut)
@limiter.limit("20/minute")
async def assign_camera_coop(
    camera_id: str,
    request: Request,
    data: AssignCoopRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("cameras:write")),
    farm_id: str | None = Depends(get_farm_id),
):
    camera = await get_camera(db, camera_id)
    if not camera:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Camera not found")
    if farm_id and str(camera.farm_id) != farm_id and user.role.name != "super_admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    camera.coop_id = data.coop_id
    await db.commit()
    await db.refresh(camera)

    cam_out = CameraOut.model_validate(camera)
    cam_out.hls_url = f"/api/frigate/hls/{camera.name}/index.m3u8"
    return cam_out


@router.delete("/{camera_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("20/minute")
async def remove_camera(
    camera_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("cameras:delete")),
    farm_id: str | None = Depends(get_farm_id),
):
    camera = await get_camera(db, camera_id)
    if not camera:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Camera not found")
    if farm_id and str(camera.farm_id) != farm_id and user.role.name != "super_admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    deleted = await delete_camera(db, camera_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Camera not found")
