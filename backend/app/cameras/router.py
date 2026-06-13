from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.deps import get_current_user, require_permission
from app.auth.models import User
from app.cameras.models import Camera, CameraStream
from app.cameras.onvif import ONVIFScanner, scanner
from app.cameras.schemas import CameraCreate, CameraOut, CameraUpdate, ONVIFDevice, ONVIFScanRequest
from app.cameras.service import create_camera, delete_camera, get_camera, list_cameras, update_camera
from app.database import get_db

router = APIRouter(prefix="/cameras", tags=["cameras"])


@router.get("", response_model=list[CameraOut])
async def get_cameras(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("cameras:read")),
):
    cameras = await list_cameras(db)
    result = []
    for cam in cameras:
        cam_out = CameraOut.model_validate(cam)
        stream_result = await db.execute(
            select(CameraStream).where(CameraStream.camera_id == cam.id)
        )
        stream = stream_result.scalar_one_or_none()
        if stream:
            cam_out.hls_url = stream.hls_url
        result.append(cam_out)
    return result


@router.get("/{camera_id}", response_model=CameraOut)
async def get_camera_detail(
    camera_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("cameras:read")),
):
    camera = await get_camera(db, camera_id)
    if not camera:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Camera not found")
    cam_out = CameraOut.model_validate(camera)
    stream_result = await db.execute(
        select(CameraStream).where(CameraStream.camera_id == camera.id)
    )
    stream = stream_result.scalar_one_or_none()
    if stream:
        cam_out.hls_url = stream.hls_url
    return cam_out


@router.post("", response_model=CameraOut, status_code=status.HTTP_201_CREATED)
async def add_camera(
    data: CameraCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("cameras:write")),
):
    camera = await create_camera(db, data)
    cam_out = CameraOut.model_validate(camera)
    stream_result = await db.execute(
        select(CameraStream).where(CameraStream.camera_id == camera.id)
    )
    stream = stream_result.scalar_one_or_none()
    if stream:
        cam_out.hls_url = stream.hls_url
    return cam_out


@router.put("/{camera_id}", response_model=CameraOut)
async def edit_camera(
    camera_id: str,
    data: CameraUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("cameras:write")),
):
    camera = await update_camera(db, camera_id, data)
    if not camera:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Camera not found")

    from app.detection.worker import orchestrator
    await orchestrator.stop_camera(camera_id)
    if camera.enabled:
        await orchestrator.start_camera(camera)

    cam_out = CameraOut.model_validate(camera)
    stream_result = await db.execute(
        select(CameraStream).where(CameraStream.camera_id == camera.id)
    )
    stream = stream_result.scalar_one_or_none()
    if stream:
        cam_out.hls_url = stream.hls_url
    return cam_out


@router.delete("/{camera_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_camera(
    camera_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("cameras:delete")),
):
    deleted = await delete_camera(db, camera_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Camera not found")

    from app.detection.worker import orchestrator
    await orchestrator.stop_camera(camera_id)


@router.post("/scan")
async def scan_network(
    background_tasks: BackgroundTasks,
    data: ONVIFScanRequest | None = None,
    user: User = Depends(require_permission("cameras:scan")),
):
    if scanner._scanning:
        return {"message": "Scan already in progress", "status": scanner.status}

    scan_kwargs = {}
    if data:
        if data.subnet:
            scan_kwargs["subnet"] = data.subnet
        if data.ip:
            scan_kwargs["ip"] = data.ip
        if data.username:
            scan_kwargs["username"] = data.username
        if data.password:
            scan_kwargs["password"] = data.password

    background_tasks.add_task(scanner.scan, **scan_kwargs)
    return {"message": "ONVIF scan started", "status": scanner.status}


@router.get("/scan/status")
async def scan_status(
    user: User = Depends(require_permission("cameras:read")),
):
    return scanner.status


@router.get("/scan/results", response_model=list[ONVIFDevice])
async def scan_results(
    user: User = Depends(require_permission("cameras:read")),
):
    return scanner._found_devices
