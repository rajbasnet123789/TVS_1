import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

logger = logging.getLogger(__name__)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_farm_id, require_permission
from app.auth.models import User
from app.cameras.models import Camera
from app.database import get_db
from app.detection.schemas import DetectionHistory, DetectionStats, DetectionSummary, TimeSeriesPoint
from app.frigate.client import get_frigate_stats, get_camera_events
from app.detection.queries import query_detection_history, query_detection_summary

router = APIRouter(prefix="/cameras/{camera_id}/detection", tags=["detection"])
global_router = APIRouter(prefix="/detection", tags=["detection"])

# Standalone MCMT global tracker (shared with subscriber via mcmt_singleton)
from app.detection.mcmt_singleton import get_mcmt_tracker
from app.rate_limit import limiter


def _validate_camera_id(camera_id: str):
    try:
        uuid.UUID(camera_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid camera ID format")


@router.post("/start")
@limiter.limit("20/minute")
async def start_detection(
    camera_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("cameras:write")),
    farm_id: str | None = Depends(get_farm_id),
):
    _validate_camera_id(camera_id)
    result = await db.execute(select(Camera).where(Camera.id == camera_id))
    camera = result.scalar_one_or_none()
    if not camera:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Camera not found")
    if farm_id and str(camera.farm_id) != farm_id and user.role.name != "super_admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    return {"status": "enabled", "camera_id": camera_id, "note": "Detection managed by Frigate; enabled in camera config"}


@router.post("/stop")
@limiter.limit("20/minute")
async def stop_detection(
    camera_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("cameras:write")),
    farm_id: str | None = Depends(get_farm_id),
):
    _validate_camera_id(camera_id)
    result = await db.execute(select(Camera).where(Camera.id == camera_id))
    camera = result.scalar_one_or_none()
    if not camera:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Camera not found")
    if farm_id and str(camera.farm_id) != farm_id and user.role.name != "super_admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    return {"status": "disabled", "camera_id": camera_id, "note": "Detection managed by Frigate; disable in camera config"}


@router.get("/status")
async def detection_status(
    camera_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("cameras:read")),
    farm_id: str | None = Depends(get_farm_id),
):
    _validate_camera_id(camera_id)
    result = await db.execute(select(Camera).where(Camera.id == camera_id))
    camera = result.scalar_one_or_none()
    if not camera:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Camera not found")
    if farm_id and str(camera.farm_id) != farm_id and user.role.name != "super_admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    try:
        frigate_stats = await get_frigate_stats()
        camera_stats = frigate_stats.get("cameras", {}).get(camera.name, {})
        detection_enabled = camera_stats.get("detection_enabled", False)
        fps = camera_stats.get("detection_fps", 0)
        return {"camera_id": camera_id, "detection_enabled": detection_enabled, "fps": fps}
    except Exception:
        return {"camera_id": camera_id, "detection_enabled": False, "fps": 0}


@router.get("/stats")
async def detection_stats(
    camera_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("cameras:read")),
    farm_id: str | None = Depends(get_farm_id),
):
    _validate_camera_id(camera_id)
    result = await db.execute(select(Camera).where(Camera.id == camera_id))
    camera = result.scalar_one_or_none()
    if not camera:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Camera not found")
    if farm_id and str(camera.farm_id) != farm_id and user.role.name != "super_admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    try:
        from app.detection.queries import validate_camera_id
        from app.detection.queries import query_detection_stats

        validate_camera_id(camera_id)
        stats = query_detection_stats(camera_id)
        frigate_stats = await get_frigate_stats()
        camera_stats = frigate_stats.get("cameras", {}).get(camera.name, {})
        active = camera_stats.get("detection_enabled", False)
        return DetectionStats(
            total_detections=stats.get("total", 0),
            unique_chickens=stats.get("unique", 0),
            detections_per_minute=round(stats.get("per_minute", 0), 1),
            active_cameras=1 if active else 0,
        )
    except Exception:
        logger.error(f"Stats query failed for camera {camera_id}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to retrieve detection stats",
        )


@router.get("/history")
async def detection_history(
    camera_id: str,
    start: str = Query("-1h"),
    end: str = Query("now()"),
    window: str = Query("5m"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("cameras:read")),
    farm_id: str | None = Depends(get_farm_id),
):
    _validate_camera_id(camera_id)
    result = await db.execute(select(Camera).where(Camera.id == camera_id))
    camera = result.scalar_one_or_none()
    if not camera:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Camera not found")
    if farm_id and str(camera.farm_id) != farm_id and user.role.name != "super_admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    try:
        detection_series, headcount_series = query_detection_history(camera_id, start, end, window)
        return DetectionHistory(
            camera_id=camera_id,
            window=window,
            detection_series=[TimeSeriesPoint(**p) for p in detection_series],
            headcount_series=[TimeSeriesPoint(**p) for p in headcount_series],
        )
    except ImportError:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="InfluxDB not available")
    except ValueError:
        logger.exception(f"Invalid query params for camera {camera_id}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid detection query parameters")
    except Exception:
        logger.exception(f"History query failed for camera {camera_id}")
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Failed to retrieve detection history")


@router.get("/summary")
async def detection_summary(
    camera_id: str,
    start: str = Query("-1h"),
    end: str = Query("now()"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("cameras:read")),
    farm_id: str | None = Depends(get_farm_id),
):
    _validate_camera_id(camera_id)
    result = await db.execute(select(Camera).where(Camera.id == camera_id))
    camera = result.scalar_one_or_none()
    if not camera:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Camera not found")
    if farm_id and str(camera.farm_id) != farm_id and user.role.name != "super_admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    try:
        summary = query_detection_summary(camera_id, start, end)
        return DetectionSummary(**summary)
    except ImportError:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="InfluxDB not available")
    except ValueError:
        logger.exception(f"Invalid query params for camera {camera_id}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid detection query parameters")
    except Exception:
        logger.exception(f"Summary query failed for camera {camera_id}")
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Failed to retrieve detection summary")


@global_router.get("/global/history")
async def global_detection_history(
    start: str = Query("-1h"),
    end: str = Query("now()"),
    window: str = Query("5m"),
    user: User = Depends(require_permission("dashboard:read")),
    farm_id: str | None = Depends(get_farm_id),
):
    try:
        from app.detection.queries import query_global_history

        detection_series, headcount_series = query_global_history(start, end, window, farm_id=farm_id)
        return DetectionHistory(
            camera_id="all",
            window=window,
            detection_series=[TimeSeriesPoint(**p) for p in detection_series],
            headcount_series=[TimeSeriesPoint(**p) for p in headcount_series],
        )
    except ImportError:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="InfluxDB not available")
    except ValueError:
        logger.exception("Invalid global history query params")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid detection query parameters")
    except Exception:
        logger.exception("Global history query failed")
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Failed to retrieve global detection history")


@global_router.get("/mcmt/identities")
async def mcmt_active_identities(
    max_age: int = Query(60, description="Max seconds since last seen"),
    farm_id: str | None = Depends(get_farm_id),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("dashboard:read")),
):
    tracker = await get_mcmt_tracker()
    identities = tracker.get_active_identities(max_age_seconds=max_age)


    return {
        "total_identities": tracker.get_total_identities(),
        "active_identities": [
            {
                "global_id": ident["global_id"],
                "camera_id": ident["camera_id"],
                "last_seen": ident["last_seen"],
                "detection_count": ident["detection_count"],
                "confidence": round(ident["confidence"], 3),
            }
            for ident in identities
        ],
    }


@global_router.get("/mcmt/gallery/stats")
async def mcmt_gallery_stats(
    farm_id: str | None = Depends(get_farm_id),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("dashboard:read")),
):
    tracker = await get_mcmt_tracker()
    gallery = tracker.gallery
    active_count = len(gallery.get_active_ids(max_age_seconds=60))

    if farm_id:
        result = await db.execute(
            select(Camera).where(Camera.farm_id == farm_id)
        )
        farm_camera_ids = {cam.name or str(cam.id) for cam in result.scalars().all()}
        active_identities = tracker.get_active_identities(max_age_seconds=60)
        farm_active = len([i for i in active_identities if i.get("camera_id") in farm_camera_ids])
        active_count = farm_active

    return {
        "total_embeddings": gallery.size(),
        "embedding_dim": gallery.embedding_dim,
        "active_count": active_count,
    }
