import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.alerts.models import Alert
from app.alerts.schemas import AlertCreate

logger = logging.getLogger(__name__)


async def create_alert(db: AsyncSession, data: AlertCreate, farm_id: str | None = None) -> Alert:
    if not farm_id:
        if data.camera_id:
            from app.cameras.models import Camera
            camera_res = await db.execute(select(Camera).where(Camera.id == data.camera_id))
            camera = camera_res.scalar_one_or_none()
            if camera and camera.farm_id:
                farm_id = str(camera.farm_id)
        if not farm_id:
            # Fallback to the documented system default farm UUID, validating that it exists in the database.
            from app.farms.models import Farm
            default_farm_uuid = '00000000-0000-0000-0000-000000000001'
            result = await db.execute(select(Farm).where(Farm.id == default_farm_uuid))
            if not result.scalar_one_or_none():
                raise ValueError("System default farm UUID does not exist in the database")
            farm_id = default_farm_uuid

    alert = Alert(
        camera_id=data.camera_id,
        chicken_id=data.chicken_id,
        track_id=data.track_id,
        type=data.type,
        severity=data.severity,
        message=data.message,
        farm_id=farm_id,
    )
    db.add(alert)
    await db.commit()
    await db.refresh(alert)
    logger.info(f"Alert created: [{data.type}] {data.message}")

    # Broadcast alert via WebSocket
    try:
        from app.websocket.manager import manager
        event = {
            "type": "alert",
            "alert_id": str(alert.id),
            "camera_id": str(alert.camera_id) if alert.camera_id else None,
            "chicken_id": alert.chicken_id,
            "alert_type": alert.type,
            "severity": alert.severity,
            "message": alert.message,
            "farm_id": str(alert.farm_id) if alert.farm_id else None,
            "timestamp": alert.created_at.isoformat() if alert.created_at else datetime.now(timezone.utc).isoformat(),
        }
        await manager.broadcast("alerts", event)
        if alert.farm_id:
            await manager.broadcast(f"farm_{alert.farm_id}/alerts", event)
    except Exception as e:
        logger.warning(f"Failed to broadcast alert: {e}")

    return alert


async def get_alerts(db: AsyncSession, limit: int = 50, offset: int = 0, farm_id: str | None = None) -> list[Alert]:
    query = select(Alert).order_by(Alert.created_at.desc())
    if farm_id:
        query = query.where(Alert.farm_id == farm_id)
    result = await db.execute(query.offset(offset).limit(limit))
    return list(result.scalars().all())


async def acknowledge_alert(db: AsyncSession, alert: Alert, farm_id: str | None = None) -> Alert | None:
    if farm_id and (alert.farm_id is None or str(alert.farm_id) != farm_id):
        return None
    alert.acknowledged_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(alert)
    return alert


async def get_unacknowledged_count(db: AsyncSession, farm_id: str | None = None) -> int:
    from sqlalchemy import func
    query = select(func.count(Alert.id)).where(Alert.acknowledged_at.is_(None))
    if farm_id:
        query = query.where(Alert.farm_id == farm_id)
    result = await db.execute(query)
    return result.scalar_one()
