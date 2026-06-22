import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.auth.models import User
from app.auth.deps import get_current_user, get_farm_id, require_permission
from app.frigate import client as frigate_client
from app.rate_limit import limiter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/frigate", tags=["frigate"])


@router.get("/stats")
async def get_frigate_stats(
    farm_id: str | None = Depends(get_farm_id),
    _: bool = Depends(require_permission("frigate:view")),
):
    try:
        return await frigate_client.get_frigate_stats()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Frigate unreachable: {e}")


async def _validate_camera_ownership(camera_name: str, db: AsyncSession, farm_id: str | None, user: User) -> None:
    from app.cameras.models import Camera
    result = await db.execute(select(Camera).where(Camera.name == camera_name))
    camera = result.scalar_one_or_none()
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")
    if user.role.name != "super_admin" and farm_id and str(camera.farm_id) != farm_id:
        raise HTTPException(status_code=403, detail="Access denied")


@router.get("/events/{camera_name}")
async def get_camera_events(
    camera_name: str,
    limit: int = 50,
    farm_id: str | None = Depends(get_farm_id),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    _: bool = Depends(require_permission("detections:view")),
):
    await _validate_camera_ownership(camera_name, db, farm_id, user)
    try:
        return await frigate_client.get_camera_events(camera_name, limit=limit)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Frigate unreachable: {e}")


@router.get("/recordings/{camera_name}")
async def get_camera_recordings(
    camera_name: str,
    before: int | None = None,
    after: int | None = None,
    limit: int = 100,
    farm_id: str | None = Depends(get_farm_id),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    _: bool = Depends(require_permission("nvr:view")),
):
    await _validate_camera_ownership(camera_name, db, farm_id, user)
    try:
        return await frigate_client.get_recordings(camera_name, before=before, after=after, limit=limit)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Frigate unreachable: {e}")


@router.post("/config/reload")
@limiter.limit("20/minute")
async def reload_frigate_config(
    request: Request,
    farm_id: str | None = Depends(get_farm_id),
    _: bool = Depends(require_permission("frigate:config")),
):
    try:
        await frigate_client.reload_config()
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Frigate unreachable: {e}")


@router.get("/stream/{camera_name}")
async def get_stream_url(
    camera_name: str,
    farm_id: str | None = Depends(get_farm_id),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    _: bool = Depends(require_permission("cameras:view")),
):
    await _validate_camera_ownership(camera_name, db, farm_id, user)
    return {"url": f"/api/frigate/hls/{camera_name}/index.m3u8", "type": "hls"}
