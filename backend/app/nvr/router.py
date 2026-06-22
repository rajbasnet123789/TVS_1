import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import require_permission, get_farm_id
from app.auth.models import User
from app.cameras.models import Camera
from app.database import get_db
from app.frigate import client as frigate_client
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
    snapshot = await frigate_client.get_snapshot(camera.name)
    if not snapshot:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="No snapshot available from Frigate")
    from fastapi.responses import Response
    return Response(content=snapshot, media_type="image/jpeg")


@router.get("/recordings/{camera_id}")
async def list_recordings(
    camera_id: str,
    before: int | None = Query(None, description="End timestamp (epoch)"),
    after: int | None = Query(None, description="Start timestamp (epoch)"),
    limit: int = Query(100, description="Max recordings"),
    user: User = Depends(require_permission("nvr:read")),
    db: AsyncSession = Depends(get_db),
    farm_id: str | None = Depends(get_farm_id),
):
    camera = await _resolve_camera(camera_id, db, farm_id, user.role.name == "super_admin")
    try:
        recordings = await frigate_client.get_recordings(camera.name, before=before, after=after, limit=limit)
        return {"recordings": recordings, "camera_id": camera_id, "camera_name": camera.name}
    except Exception as e:
        logger.warning("Failed to list recordings from Frigate: %s", e)
        return {"recordings": [], "camera_id": camera_id, "camera_name": camera.name}


@router.get("/playback-url/{camera_id}")
async def get_playback_url(
    camera_id: str,
    at: str = Query(..., description="Playback start time (ISO 8601)"),
    user: User = Depends(require_permission("nvr:read")),
    db: AsyncSession = Depends(get_db),
    farm_id: str | None = Depends(get_farm_id),
):
    camera = await _resolve_camera(camera_id, db, farm_id, user.role.name == "super_admin")
    try:
        at_ts = int(datetime.fromisoformat(at).timestamp())
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid datetime format: {e}")

    recordings = await frigate_client.get_recordings(camera.name, before=at_ts + 3600, after=at_ts - 300, limit=1)
    start_ts = at_ts
    end_ts = at_ts + 14400
    hls_url = f"/api/frigate/vod/{camera.name}/start/{start_ts}/end/{end_ts}/index.m3u8"
    return {
        "playback_url": hls_url,
        "recording_start": recordings[0]["start_time"] if recordings else None,
        "camera_id": camera_id,
        "camera_name": camera.name,
    }


@router.get("/storage")
async def get_storage(
    _: User = Depends(require_permission("nvr:read")),
):
    try:
        stats = await frigate_client.get_frigate_stats()
        storage = stats.get("service", {}).get("storage", {})
        total_bytes = storage.get("total", 0)
        used_bytes = storage.get("used", 0)
        free_bytes = total_bytes - used_bytes
        usage_pct = round((used_bytes / total_bytes * 100), 1) if total_bytes > 0 else 0
        return {
            "total_bytes": total_bytes,
            "free_bytes": free_bytes,
            "used_bytes": used_bytes,
            "usage_percent": usage_pct,
        }
    except Exception as e:
        logger.warning("Failed to get storage from Frigate: %s", e)
        total_bytes = 500 * 1024 * 1024 * 1024
        return {"total_bytes": total_bytes, "free_bytes": total_bytes, "used_bytes": 0, "usage_percent": 0}


@router.get("/channels")
async def get_channels(
    user: User = Depends(require_permission("nvr:read")),
    db: AsyncSession = Depends(get_db),
    farm_id: str | None = Depends(get_farm_id),
):
    try:
        stats = await frigate_client.get_frigate_stats()
        cameras = stats.get("cameras", {})
        channels = [
            {
                "index": str(i),
                "Name": name,
                "Online": cam_info.get("enabled", False),
                "detection_fps": cam_info.get("detection_fps", 0),
                "capture_fps": cam_info.get("camera_fps", 0),
            }
            for i, (name, cam_info) in enumerate(cameras.items())
        ]
        return {"channels": channels}
    except Exception:
        from app.cameras.models import Camera
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
    at: str = Query(..., description="Playback start time (ISO 8601)"),
    user: User = Depends(require_permission("nvr:read")),
    db: AsyncSession = Depends(get_db),
    farm_id: str | None = Depends(get_farm_id),
):
    camera = await _resolve_camera(camera_id, db, farm_id, user.role.name == "super_admin")
    try:
        at_dt = datetime.fromisoformat(at)
        at_ts = int(at_dt.timestamp())
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid datetime format: {e}")

    recordings = await frigate_client.get_recordings(camera.name, before=at_ts + 3600, after=at_ts - 300, limit=1)
    start_ts = at_ts
    end_ts = at_ts + 14400
    hls_url = f"/api/frigate/vod/{camera.name}/start/{start_ts}/end/{end_ts}/index.m3u8"
    import uuid
    return {
        "session_id": f"playback-{camera_id}-{uuid.uuid4()}",
        "hls_url": hls_url,
        "camera_id": camera_id,
        "camera_name": camera.name,
        "recording_start": recordings[0]["start_time"] if recordings else None,
    }


@router.post("/playback/stop")
@limiter.limit("20/minute")
async def stop_playback(
    request: Request,
    session_id: str = Query(...),
    _: User = Depends(require_permission("nvr:read")),
):
    return {"status": "stopped", "session_id": session_id}
