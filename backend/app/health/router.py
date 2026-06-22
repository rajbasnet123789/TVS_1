import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.auth.deps import get_farm_id, require_permission
from app.auth.models import User
from app.health.queries import query_health_scores, query_health_summary
from app.health.schemas import HealthRecord, HealthSummary, TimeSeriesPoint

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/scores", response_model=list[HealthRecord])
async def list_health_scores(
    camera_id: str | None = Query(None),
    start: str = Query("-1h"),
    end: str = Query("now()"),
    limit: int = Query(100, ge=1, le=1000),
    user: User = Depends(require_permission("dashboard:read")),
    farm_id: str | None = Depends(get_farm_id),
):
    try:
        results = await query_health_scores(camera_id=camera_id, start=start, end=end, limit=limit, farm_id=farm_id)
        return [
            HealthRecord(
                camera_id=r["camera_id"],
                track_id=int(r["track_id"]) if r.get("track_id") and r["track_id"] != "-1" else None,
                health_class=r.get("health_class", "unknown"),
                health_score=r["health_score"],
                health_confidence=0.0,  # Hardcoded to 0.0 as health confidence metrics are not currently provided by the model
                timestamp=r["time"],
            )
            for r in results
        ]
    except ValueError as e:
        logger.warning(f"Invalid health parameter: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.exception("Health scores query failed")
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Health query database/API connection failed")


@router.get("/summary", response_model=HealthSummary)
async def health_summary(
    camera_id: str | None = Query(None),
    start: str = Query("-24h"),
    end: str = Query("now()"),
    user: User = Depends(require_permission("dashboard:read")),
    farm_id: str | None = Depends(get_farm_id),
):
    try:
        summary = await query_health_summary(camera_id=camera_id, start=start, end=end, farm_id=farm_id)
        return HealthSummary(**summary)
    except ValueError as e:
        logger.warning(f"Invalid health summary parameter: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.exception("Health summary query failed")
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Health summary database/API connection failed")
