import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.cameras.models import Camera
from app.cameras.schemas import CameraCreate, CameraUpdate
from app.security import decrypt_camera_password, encrypt_camera_password

logger = logging.getLogger(__name__)


async def create_camera(db: AsyncSession, data: CameraCreate, farm_id: str) -> Camera:
    camera = Camera(
        name=data.name,
        rtsp_url=data.rtsp_url,
        location=data.location,
        zone=data.zone,
        fps_target=data.fps_target,
        resolution_width=data.resolution_width,
        resolution_height=data.resolution_height,
        username=data.username,
        password_hash=encrypt_camera_password(data.password) if data.password else None,
        farm_id=farm_id,
        coop_id=data.coop_id,
        snapshot_url=data.snapshot_url,
        roi=data.roi,
    )
    db.add(camera)
    await db.commit()
    await db.refresh(camera)
    logger.info(f"Camera {camera.name} created")
    return camera


async def update_camera(db: AsyncSession, camera_id: str, data: CameraUpdate) -> Camera | None:
    result = await db.execute(select(Camera).where(Camera.id == camera_id))
    camera = result.scalar_one_or_none()
    if not camera:
        return None

    update_data = data.model_dump(exclude_unset=True)
    if "password" in update_data:
        pw = update_data.pop("password")
        update_data["password_hash"] = encrypt_camera_password(pw) if pw else None

    for key, value in update_data.items():
        setattr(camera, key, value)

    await db.commit()
    await db.refresh(camera)
    logger.info(f"Camera {camera.name} updated")
    return camera


async def delete_camera(db: AsyncSession, camera_id: str) -> bool:
    result = await db.execute(select(Camera).where(Camera.id == camera_id))
    camera = result.scalar_one_or_none()
    if not camera:
        return False

    await db.delete(camera)
    await db.commit()
    logger.info(f"Camera {camera.name} deleted")
    return True


async def get_camera(db: AsyncSession, camera_id: str) -> Camera | None:
    result = await db.execute(select(Camera).where(Camera.id == camera_id))
    return result.scalar_one_or_none()


async def list_cameras(db: AsyncSession, farm_id: str | None = None) -> list[Camera]:
    query = select(Camera)
    if farm_id:
        query = query.where(Camera.farm_id == farm_id)
    result = await db.execute(query.order_by(Camera.created_at.desc()))
    return result.scalars().all()
