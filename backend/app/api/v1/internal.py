"""Internal API endpoints for service-to-service communication (cv-engine)."""
import logging
from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.cameras.models import Camera
from app.database import get_db
from app.alerts.models import AlertRule, Alert
from app.alerts.service import create_alert
from app.alerts.schemas import AlertCreate
from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/internal", tags=["internal"])


def _require_internal_token(
    x_internal_token: str | None = Header(None, alias="X-Internal-Token"),
) -> None:
    """Validate that requests to internal endpoints come from the cv-engine."""
    configured_key = settings.cv_engine_api_key
    if not configured_key:
        # Key not configured — warn in dev, still allow (backwards compat)
        logger.warning(
            "CV_ENGINE_API_KEY is not set. Internal endpoints are unprotected. "
            "Set CV_ENGINE_API_KEY in .env for production deployments."
        )
        return
    if x_internal_token != configured_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or missing internal service token.",
        )


@router.get("/fix-channels")
@router.post("/fix-channels")
async def fix_camera_channels_internal(
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import delete
    from app.farms.models import Farm

    farm_res = await db.execute(select(Farm).limit(1))
    farm = farm_res.scalar_one_or_none()
    farm_id = farm.id if farm else None

    # Wipe all existing camera entries to guarantee zero stale worker connections
    await db.execute(delete(Camera))
    await db.commit()

    # Recreate exactly 5 clean active camera entries (Channels 0..4)
    cameras = []
    for idx in range(5):
        ch = idx + 1
        cam = Camera(
            farm_id=farm_id,
            name=f"Camera {ch} (Ch {ch})",
            rtsp_url=f"dvrip://apap:3tr65t@192.168.31.169:34567/{idx}",
            location=f"NVR Channel {ch}",
            status="online",
            enabled=True,
        )
        db.add(cam)
        cameras.append({"name": f"Camera {ch} (Ch {ch})", "dvrip_channel": idx, "rtsp_url": cam.rtsp_url})

    await db.commit()
    return {"status": "ok", "created_count": len(cameras), "cameras": cameras}


@router.get("/reset-cameras")
@router.post("/reset-cameras")
async def reset_cameras_internal(
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import delete
    result = await db.execute(delete(Camera))
    await db.commit()
    return {"status": "ok", "message": "All camera records deleted successfully"}


@router.get("/cameras")
async def list_active_cameras(
    db: AsyncSession = Depends(get_db),
    _: None = Depends(_require_internal_token),
):
    """Return all enabled cameras for cv-engine to process."""
    result = await db.execute(
        select(Camera).where(Camera.enabled == True)
    )
    cameras = result.scalars().all()
    return {
        "cameras": [
            {
                "id": str(cam.id),
                "name": cam.name,
                "rtsp_url": cam.rtsp_url,
                "farm_id": str(cam.farm_id),
                "fps_target": cam.fps_target,
                "resolution_width": cam.resolution_width,
                "resolution_height": cam.resolution_height,
                "username": cam.username,
                "roi": cam.roi,
                "status": cam.status,
            }
            for cam in cameras
        ]
    }


@router.get("/alert-rules")
async def list_active_alert_rules(
    db: AsyncSession = Depends(get_db),
    _: None = Depends(_require_internal_token),
):
    """Return enabled alert rules for cv-engine to evaluate."""
    result = await db.execute(select(AlertRule).where(AlertRule.enabled == True))
    rules = result.scalars().all()
    return {
        "rules": [
            {
                "id": str(rule.id),
                "name": rule.name,
                "metric": rule.metric,
                "threshold": rule.threshold,
                "window_minutes": getattr(rule, "duration_minutes", 30),
                "severity": rule.severity,
                "farm_id": str(rule.farm_id) if rule.farm_id else None,
                "camera_id": None,
            }
            for rule in rules
        ]
    }


@router.post("/alerts")
async def create_alert_internal(
    data: AlertCreate,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(_require_internal_token),
):
    """Create an alert (called by cv-engine)."""
    alert = await create_alert(db, data, data.farm_id if hasattr(data, 'farm_id') else None)
    return {"alert_id": str(alert.id), "status": "created"}
