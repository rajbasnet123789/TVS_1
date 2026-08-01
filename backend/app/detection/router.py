import asyncio
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
from app.detection.queries import query_detection_history, query_detection_summary
from app.detection.schemas import (
    DetectionHistory,
    DetectionStats,
    DetectionSummary,
    TimeSeriesPoint,
)
from app.rate_limit import limiter

router = APIRouter(prefix="/cameras/{camera_id}/detection", tags=["detection"])
global_router = APIRouter(prefix="/detection", tags=["detection"])


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
    return {"status": "enabled", "camera_id": camera_id}


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
    return {"status": "disabled", "camera_id": camera_id}


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
    return {"camera_id": camera_id, "detection_enabled": camera.enabled, "fps": 0}


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
        from app.detection.queries import query_detection_stats, validate_camera_id
        validate_camera_id(camera_id)
        stats = await asyncio.to_thread(query_detection_stats, camera_id)
        return DetectionStats(
            total_detections=stats.get("total", 0),
            unique_chickens=stats.get("unique", 0),
            detections_per_minute=round(stats.get("per_minute", 0), 1),
            active_cameras=1 if camera.enabled else 0,
        )
    except Exception:
        logger.exception(f"Stats query failed for camera {camera_id}")
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
        detection_series, headcount_series = await asyncio.to_thread(query_detection_history, camera_id, start, end, window)
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
        summary = await asyncio.to_thread(query_detection_summary, camera_id, start, end)
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
        detection_series, headcount_series = await asyncio.to_thread(query_global_history, start, end, window, farm_id=farm_id)
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


@global_router.get("/live-counts")
async def live_per_camera_counts(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("dashboard:read")),
    farm_id: str | None = Depends(get_farm_id),
):
    """Return the count of unique chickens (by track_id) seen per camera in the last 15 minutes.

    Response: [{camera_id, camera_name, count}] sorted by camera name.
    """
    try:
        from app.detection.queries import query_per_camera_live_counts
        counts = await asyncio.to_thread(query_per_camera_live_counts, farm_id=farm_id, window_minutes=15)
        count_map = {r["camera_id"]: r["count"] for r in counts}

        # Query all cameras in PostgreSQL for this farm so every camera gets an entry
        if farm_id:
            result = await db.execute(select(Camera).where(Camera.farm_id == farm_id))
        else:
            result = await db.execute(select(Camera))
        all_cameras = result.scalars().all()

        enriched = [
            {
                "camera_id": str(cam.id),
                "camera_name": cam.name,
                "count": count_map.get(str(cam.id), 0),
            }
            for cam in all_cameras
        ]
        # Sort by camera name so channels appear in order
        enriched.sort(key=lambda x: x["camera_name"])
        return enriched
    except ImportError:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="InfluxDB not available")
    except Exception:
        logger.exception("Live counts query failed")
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Failed to retrieve live counts")

