from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.auth.deps import get_farm_id, require_permission
from app.auth.models import User
from app.chickens.schemas import DetectedChicken

router = APIRouter(prefix="/chickens", tags=["chickens"])


@router.get("/detected", response_model=list[DetectedChicken])
async def get_detected_chickens(
    start: str = Query("-1h"),
    end: str = Query("now()"),
    user: User = Depends(require_permission("chickens:read")),
    farm_id: str | None = Depends(get_farm_id),
):
    try:
        from app.detection.queries import query_detected_chickens

        results = query_detected_chickens(start, end, farm_id=farm_id)
        return [DetectedChicken(**r) for r in results]
    except ImportError:
        return []
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Detection query failed: {e}")
