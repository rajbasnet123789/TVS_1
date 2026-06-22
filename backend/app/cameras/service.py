import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.cameras.models import Camera
from app.cameras.schemas import CameraCreate, CameraUpdate
from app.frigate.config_manager import add_camera_to_frigate, remove_camera_from_frigate, update_camera_in_frigate
from app.frigate.client import reload_config
from app.frigate.schemas import FrigateCameraConfig
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

    await _register_in_frigate(camera)
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

    await _update_in_frigate(camera)
    return camera


async def delete_camera(db: AsyncSession, camera_id: str) -> bool:
    result = await db.execute(select(Camera).where(Camera.id == camera_id))
    camera = result.scalar_one_or_none()
    if not camera:
        return False

    await _remove_from_frigate(camera)
    await db.delete(camera)
    await db.commit()
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


async def _register_in_frigate(camera: Camera):
    try:
        plain = decrypt_camera_password(camera.password_hash) if camera.password_hash else None
        cfg = FrigateCameraConfig(
            name=camera.name,
            rtsp_url=camera.rtsp_url,
            username=camera.username or None,
            password=plain,
            enabled=camera.enabled,
        )
        await add_camera_to_frigate(cfg)
        await reload_config()
        logger.info(f"Camera {camera.name} registered in Frigate")
    except Exception as e:
        logger.warning(f"Failed to register camera {camera.name} in Frigate: {e}")


async def _update_in_frigate(camera: Camera):
    try:
        plain = decrypt_camera_password(camera.password_hash) if camera.password_hash else None
        cfg = FrigateCameraConfig(
            name=camera.name,
            rtsp_url=camera.rtsp_url,
            username=camera.username or None,
            password=plain,
            enabled=camera.enabled,
        )
        await update_camera_in_frigate(cfg)
        await reload_config()
        logger.info(f"Camera {camera.name} updated in Frigate")
    except Exception as e:
        logger.warning(f"Failed to update camera {camera.name} in Frigate: {e}")


async def _remove_from_frigate(camera: Camera):
    try:
        await remove_camera_from_frigate(camera.name)
        await reload_config()
        logger.info(f"Camera {camera.name} removed from Frigate")
    except Exception as e:
        logger.warning(f"Failed to remove camera {camera.name} from Frigate: {e}")


