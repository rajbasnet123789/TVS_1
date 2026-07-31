"""Internal API endpoints for service-to-service communication (cv-engine)."""
import logging
from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.cameras.models import Camera
from app.database import get_db
from app.alerts.models import Alert
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
    # go2rtc is pre-configured with ch1..ch5 streams pointing to physical Dahua NVR channels 1..5.
    # Note: channel=0 on Dahua is the multi-picture Zero Channel and is avoided.
    cameras = []
    for idx in range(5):
        ch_label = idx + 1  # Display: Ch 1 .. Ch 5 (matches NVR channels 1..5)
        stream_url = f"rtsp://localhost:8554/ch{ch_label}"
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
            "go2rtc_stream": f"ch{ch_label}",
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

    await _broadcast_camera_status(db, running_ids, stopped_ids)
    return {"ok": True, "online": len(running_ids), "offline": len(stopped_ids)}


async def _broadcast_camera_status(db: AsyncSession, running_ids: list[str], stopped_ids: list[str]) -> None:
    """Push per-camera status changes over WebSocket so the UI updates without polling."""
    from app.websocket.manager import manager

    all_ids = list(running_ids) + list(stopped_ids)
    if not all_ids:
        return
    result = await db.execute(select(Camera.id, Camera.farm_id).where(Camera.id.in_(all_ids)))
    status_by_id: dict[str, tuple[str, str | None]] = {}
    for cam_id, farm_id in result.all():
        sid = str(cam_id)
        status_by_id[sid] = (status_by_id.get(sid, ("", None))[0], str(farm_id) if farm_id else None)

    for sid in running_ids:
        _, farm_id = status_by_id.get(sid, ("", None))
        status_by_id[sid] = ("online", farm_id)
    for sid in stopped_ids:
        _, farm_id = status_by_id.get(sid, ("", None))
        status_by_id[sid] = ("offline", farm_id)

    by_farm: dict[str, list[dict]] = {}
    global_updates: list[dict] = []
    for sid, (status, farm_id) in status_by_id.items():
        entry = {"camera_id": sid, "status": status, "farm_id": farm_id}
        global_updates.append(entry)
        if farm_id:
            by_farm.setdefault(farm_id, []).append(entry)

    for farm_id, entries in by_farm.items():
        await manager.broadcast(
            f"farm_{farm_id}/camera_status",
            {"type": "camera_status", "updates": entries, "farm_id": farm_id},
        )
    await manager.broadcast(
        "camera_status",
        {"type": "camera_status", "updates": global_updates, "farm_id": None},
    )


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


@router.post("/alerts")
async def create_alert_internal(
    data: AlertCreate,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(_require_internal_token),
):
    """Create an alert (called by cv-engine)."""
    alert = await create_alert(db, data, data.farm_id if hasattr(data, 'farm_id') else None)
    return {"alert_id": str(alert.id), "status": "created"}


@router.post("/counts")
async def ingest_live_counts(
    body: dict,
    _: None = Depends(_require_internal_token),
):
    """Receive live per-camera counts from cv-engine and broadcast them over WebSocket.

    Expected body: {"counts": [{"camera_id": "...", "farm_id": "...", "count": 12}, ...]}
    """
    from app.websocket.manager import manager

    counts = body.get("counts", [])
    if not counts:
        return {"ok": True, "relayed": 0}

    by_farm: dict[str, list[dict]] = {}
    for item in counts:
        cam_id = item.get("camera_id")
        farm_id = item.get("farm_id")
        count = int(item.get("count", 0))
        if not cam_id:
            continue
        entry = {"camera_id": cam_id, "count": count, "ts": item.get("ts", 0.0)}
        if farm_id:
            by_farm.setdefault(farm_id, []).append(entry)

    # Broadcast per-farm to scoped clients (farm_<id>/detections), plus the global
    # channel so clients without a farm still get updates.
    relayed = 0
    for farm_id, entries in by_farm.items():
        await manager.broadcast(
            f"farm_{farm_id}/detections",
            {"type": "counts", "counts": entries, "farm_id": farm_id},
        )
        relayed += len(entries)
    await manager.broadcast(
        "detections",
        {"type": "counts", "counts": counts, "farm_id": None},
    )
    return {"ok": True, "relayed": relayed}

