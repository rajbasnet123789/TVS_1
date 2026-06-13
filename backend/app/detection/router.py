from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import require_permission
from app.auth.models import User
from app.cameras.models import Camera
from app.database import get_db
from app.detection.schemas import DetectionHistory, DetectionStats, DetectionSummary, TimeSeriesPoint
from app.detection.worker import orchestrator

router = APIRouter(prefix="/cameras/{camera_id}/detection", tags=["detection"])
global_router = APIRouter(prefix="/detection", tags=["detection"])


@router.post("/start")
async def start_detection(
    camera_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("cameras:write")),
):
    result = await db.execute(select(Camera).where(Camera.id == camera_id))
    camera = result.scalar_one_or_none()
    if not camera:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Camera not found")
    await orchestrator.start_camera(camera)
    return {"status": "started", "camera_id": camera_id}


@router.post("/stop")
async def stop_detection(
    camera_id: str,
    user: User = Depends(require_permission("cameras:write")),
):
    await orchestrator.stop_camera(camera_id)
    return {"status": "stopped", "camera_id": camera_id}


@router.get("/status")
async def detection_status(
    camera_id: str,
    user: User = Depends(require_permission("cameras:read")),
):
    running = orchestrator.get_status(camera_id)
    return {"camera_id": camera_id, "detection_enabled": running}


@router.get("/stats")
async def detection_stats(
    camera_id: str,
    user: User = Depends(require_permission("cameras:read")),
):
    try:
        from influxdb_client import InfluxDBClient
        from app.config import settings

        client = InfluxDBClient(
            url=settings.influx_url,
            token=settings.influx_token,
            org=settings.influx_org,
        )
        query = f'''
            from(bucket: "{settings.influx_bucket}")
                |> range(start: -5m)
                |> filter(fn: (r) => r["camera_id"] == "{camera_id}")
                |> count()
        '''
        tables = client.query_api().query(query)
        total = 0
        for table in tables:
            for record in table.records:
                total += record.get_value() or 0

        unique_query = f'''
            from(bucket: "{settings.influx_bucket}")
                |> range(start: -5m)
                |> filter(fn: (r) => r["camera_id"] == "{camera_id}")
                |> distinct(column: "track_id")
        '''
        unique_tables = client.query_api().query(unique_query)
        unique_ids = set()
        for table in unique_tables:
            for record in table.records:
                unique_ids.add(record.get_value())

        client.close()
        return DetectionStats(
            total_detections=total,
            unique_chickens=len(unique_ids),
            detections_per_minute=round(total / 5, 1),
            active_cameras=1 if orchestrator.get_status(camera_id) else 0,
        )
    except ImportError:
        return DetectionStats()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"InfluxDB query failed: {e}",
        )


@router.get("/history")
async def detection_history(
    camera_id: str,
    start: str = Query("-1h"),
    end: str = Query("now()"),
    window: str = Query("5m"),
    user: User = Depends(require_permission("cameras:read")),
):
    try:
        from app.detection.queries import query_detection_history

        detection_series, headcount_series = query_detection_history(camera_id, start, end, window)
        return DetectionHistory(
            camera_id=camera_id,
            window=window,
            detection_series=[TimeSeriesPoint(**p) for p in detection_series],
            headcount_series=[TimeSeriesPoint(**p) for p in headcount_series],
        )
    except ImportError:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="InfluxDB not available")
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Query failed: {e}")


@router.get("/summary")
async def detection_summary(
    camera_id: str,
    start: str = Query("-1h"),
    end: str = Query("now()"),
    user: User = Depends(require_permission("cameras:read")),
):
    try:
        from app.detection.queries import query_detection_summary

        summary = query_detection_summary(camera_id, start, end)
        return DetectionSummary(**summary)
    except ImportError:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="InfluxDB not available")
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Query failed: {e}")


@global_router.get("/global/history")
async def global_detection_history(
    start: str = Query("-1h"),
    end: str = Query("now()"),
    window: str = Query("5m"),
    user: User = Depends(require_permission("dashboard:read")),
):
    try:
        from app.detection.queries import query_global_history

        detection_series, headcount_series = query_global_history(start, end, window)
        return DetectionHistory(
            camera_id="all",
            window=window,
            detection_series=[TimeSeriesPoint(**p) for p in detection_series],
            headcount_series=[TimeSeriesPoint(**p) for p in headcount_series],
        )
    except ImportError:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="InfluxDB not available")
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Query failed: {e}")


@global_router.get("/mcmt/identities")
async def mcmt_active_identities(
    max_age: int = Query(60, description="Max seconds since last seen"),
    user: User = Depends(require_permission("dashboard:read")),
):
    identities = orchestrator.global_tracker.get_active_identities(max_age_seconds=max_age)
    return {
        "total_identities": orchestrator.global_tracker.get_total_identities(),
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
    user: User = Depends(require_permission("dashboard:read")),
):
    gallery = orchestrator.global_tracker.gallery
    return {
        "total_embeddings": gallery.size(),
        "embedding_dim": gallery.embedding_dim,
        "active_count": len(gallery.get_active_ids(max_age_seconds=60)),
    }
