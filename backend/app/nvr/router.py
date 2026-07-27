import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import require_permission, get_farm_id
from app.auth.models import User
from app.cameras.models import Camera
from app.database import get_db
from app.rate_limit import limiter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/nvr", tags=["nvr"])


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


@router.get("/recordings/{camera_id}")
async def list_recordings(
    camera_id: str,
    before: int | None = Query(None),
    after: int | None = Query(None),
    limit: int = Query(100),
    user: User = Depends(require_permission("nvr:read")),
    db: AsyncSession = Depends(get_db),
    farm_id: str | None = Depends(get_farm_id),
):
    camera = await _resolve_camera(camera_id, db, farm_id, user.role.name == "super_admin")
    return {"recordings": [], "camera_id": camera_id, "camera_name": camera.name, "note": "Recordings not yet implemented"}


@router.get("/playback-url/{camera_id}")
async def get_playback_url(
    camera_id: str,
    at: str = Query(..., description="Playback start time (ISO 8601)"),
    user: User = Depends(require_permission("nvr:read")),
    db: AsyncSession = Depends(get_db),
    farm_id: str | None = Depends(get_farm_id),
):
    camera = await _resolve_camera(camera_id, db, farm_id, user.role.name == "super_admin")
    raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Recordings not yet implemented")


@router.get("/storage")
async def get_storage(
    _: User = Depends(require_permission("nvr:read")),
):
    total_bytes = 500 * 1024 * 1024 * 1024
    return {"total_bytes": total_bytes, "free_bytes": total_bytes, "used_bytes": 0, "usage_percent": 0}


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
    return {"nvr_time": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")}


@router.post("/playback/start/{camera_id}")
@limiter.limit("20/minute")
async def start_playback(
    camera_id: str,
    request: Request,
    at: str = Query(...),
    user: User = Depends(require_permission("nvr:read")),
    db: AsyncSession = Depends(get_db),
    farm_id: str | None = Depends(get_farm_id),
):
    raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Recordings not yet implemented")


@router.post("/playback/stop")
@limiter.limit("20/minute")
async def stop_playback(
    request: Request,
    session_id: str = Query(...),
    _: User = Depends(require_permission("nvr:read")),
):
    return {"status": "stopped", "session_id": session_id}
