"""Internal API endpoints for service-to-service communication (cv-engine)."""
import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.cameras.models import Camera
from app.database import get_db
from app.alerts.models import AlertRule, Alert
from app.alerts.service import create_alert
from app.alerts.schemas import AlertCreate
from app.websocket.manager import manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/internal", tags=["internal"])


@router.get("/cameras")
async def list_active_cameras(db: AsyncSession = Depends(get_db)):
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
async def list_active_alert_rules(db: AsyncSession = Depends(get_db)):
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
async def create_alert_internal(data: AlertCreate, db: AsyncSession = Depends(get_db)):
    """Create an alert (called by cv-engine)."""
    alert = await create_alert(db, data, data.farm_id if hasattr(data, 'farm_id') else None)
    return {"alert_id": str(alert.id), "status": "created"}
