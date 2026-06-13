import asyncio
import httpx
import logging

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.cameras.models import Camera, CameraStream
from app.cameras.schemas import CameraCreate, CameraUpdate
from app.config import settings
from app.database import async_session

logger = logging.getLogger(__name__)


async def create_camera(db: AsyncSession, data: CameraCreate) -> Camera:
    camera = Camera(
        name=data.name,
        rtsp_url=data.rtsp_url,
        onvif_address=data.onvif_address,
        location=data.location,
        zone=data.zone,
        fps_target=data.fps_target,
        resolution_width=data.resolution_width,
        resolution_height=data.resolution_height,
        username=data.username,
        password_hash=data.password,
    )
    db.add(camera)
    await db.commit()
    await db.refresh(camera)

    await _create_mediamtx_stream(camera)
    return camera


async def update_camera(db: AsyncSession, camera_id: str, data: CameraUpdate) -> Camera | None:
    result = await db.execute(select(Camera).where(Camera.id == camera_id))
    camera = result.scalar_one_or_none()
    if not camera:
        return None

    update_data = data.model_dump(exclude_unset=True)
    if "password" in update_data:
        update_data["password_hash"] = update_data.pop("password")

    for key, value in update_data.items():
        setattr(camera, key, value)

    await db.commit()
    await db.refresh(camera)
    return camera


async def delete_camera(db: AsyncSession, camera_id: str) -> bool:
    result = await db.execute(select(Camera).where(Camera.id == camera_id))
    camera = result.scalar_one_or_none()
    if not camera:
        return False

    await _delete_mediamtx_stream(db, camera)
    await db.delete(camera)
    await db.commit()
    return True


async def get_camera(db: AsyncSession, camera_id: str) -> Camera | None:
    result = await db.execute(select(Camera).where(Camera.id == camera_id))
    return result.scalar_one_or_none()


async def list_cameras(db: AsyncSession) -> list[Camera]:
    result = await db.execute(select(Camera).order_by(Camera.created_at.desc()))
    return result.scalars().all()


async def _create_mediamtx_stream(camera: Camera):
    cam_index = str(camera.id).split("-")[0]
    path_name = f"cam_{cam_index}"
    try:
        async with httpx.AsyncClient() as client:
            is_rtsp = camera.rtsp_url.startswith("rtsp://")
            if is_rtsp and camera.username:
                source = f"rtsp://{camera.username}:{camera.password_hash}@{camera.rtsp_url.replace('rtsp://', '')}"
            elif is_rtsp:
                source = camera.rtsp_url
            else:
                source = "publisher"

            payload = {
                "source": source,
                "sourceOnDemand": is_rtsp,
                "sourceOnDemandStartTimeout": "10s",
                "sourceOnDemandCloseAfter": "10s",
            }
            await client.post(
                f"{settings.mediamtx_api_url}/v3/config/paths/add/{path_name}",
                json=payload,
                auth=(settings.mediamtx_api_user, settings.mediamtx_api_pass),
            )
            logger.info(f"Created MediaMTX stream path '{path_name}' for camera {camera.name} (source={source})")
    except Exception as e:
        logger.warning(f"Failed to create MediaMTX stream for {camera.name}: {e}")

    hls_url = f"/{path_name}/index.m3u8"
    stream = CameraStream(camera_id=camera.id, mediamtx_path=path_name, hls_url=hls_url)
    async with async_session() as session:
        session.add(stream)
        await session.commit()


async def _delete_mediamtx_stream(db: AsyncSession, camera: Camera):
    result = await db.execute(select(CameraStream).where(CameraStream.camera_id == camera.id))
    stream = result.scalar_one_or_none()
    if stream:
        try:
            async with httpx.AsyncClient() as client:
                await client.delete(
                    f"{settings.mediamtx_api_url}/v3/config/paths/delete/{stream.mediamtx_path}",
                    auth=(settings.mediamtx_api_user, settings.mediamtx_api_pass),
                )
        except Exception as e:
            logger.warning(f"Failed to delete MediaMTX stream: {e}")


