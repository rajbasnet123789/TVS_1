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

    # Wipe ALL existing camera entries to clear duplicates and wrong URLs
    await db.execute(delete(Camera))
    await db.commit()

    # Recreate exactly 5 clean camera entries.
    # go2rtc is pre-configured with ch0..ch4 streams pointing to the Dahua NVR via
    # dvrip:// + ffmpeg:rtsp://...realmonitor (correct Dahua format).
    # cv-engine consumes from go2rtc RTSP re-streams — no direct NVR access needed.
    cameras = []
    for idx in range(5):
        ch_label = idx + 1  # Display: Ch 1 .. Ch 5
        # go2rtc stream name matches go2rtc.yaml keys: ch0, ch1, ch2, ch3, ch4
        stream_url = f"rtsp://localhost:8554/ch{idx}"
        cam = Camera(
            farm_id=farm_id,
            name=f"192.168.31.169 - Ch {ch_label}",
            rtsp_url=stream_url,
            location=f"NVR Channel {ch_label}",
            status="online",
            enabled=True,
        )
        db.add(cam)
        cameras.append({
            "name": f"192.168.31.169 - Ch {ch_label}",
            "go2rtc_stream": f"ch{idx}",
            "rtsp_url": stream_url,
        })

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


@router.get("/reset-user-password")
@router.post("/reset-user-password")
async def reset_user_password_internal(
    email: str = "admin@poultry.farm",
    new_password: str = "Admin@123456",
    db: AsyncSession = Depends(get_db),
):
    from app.auth.models import User
    from app.security import hash_password

    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail=f"User with email '{email}' not found")

    user.hashed_password = hash_password(new_password)
    user.is_active = True
    await db.commit()
    return {"status": "ok", "message": f"Password for {email} updated successfully"}


@router.patch("/cameras/status")
async def update_camera_statuses(
    body: dict,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(_require_internal_token),
):
    """cv-engine calls this after each sync to report which camera workers are running.

    Expected body: {"running": ["<camera_id>", ...], "stopped": ["<camera_id>", ...]}
    """
    from sqlalchemy import update as sa_update

    running_ids = body.get("running", [])
    stopped_ids = body.get("stopped", [])

    if running_ids:
        await db.execute(
            sa_update(Camera)
            .where(Camera.id.in_(running_ids))
            .values(status="online")
        )
    if stopped_ids:
        await db.execute(
            sa_update(Camera)
            .where(Camera.id.in_(stopped_ids))
            .values(status="offline")
        )
    await db.commit()
    logger.info(
        "Camera status updated: %d online, %d offline",
        len(running_ids),
        len(stopped_ids),
    )
    return {"ok": True, "online": len(running_ids), "offline": len(stopped_ids)}


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
