import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import router as api_v1_router
from app.api.v1.router import websocket_router
from app.config import settings
from app.database import init_db
from app.auth.service import seed_roles, seed_super_admin

logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up...")
    await init_db()
    from app.database import async_session
    async with async_session() as db:
        await seed_roles(db)
        await seed_super_admin(db)
        await db.commit()

    from sqlalchemy import select
    from app.cameras.models import Camera
    async with async_session() as db:
        result = await db.execute(select(Camera))
        cameras = result.scalars().all()
        if not cameras:
            from app.cameras.service import create_camera
            from app.cameras.schemas import CameraCreate
            default_cam = CameraCreate(
                name="Main Barn Camera",
                rtsp_url="rtsp://mediamtx:8554/testcam",
                location="Pen A",
                zone="Coop 1",
                fps_target=5,
                resolution_width=640,
                resolution_height=360
            )
            cam = await create_camera(db, default_cam)
            await db.commit()
            cameras = [cam]
            logger.info("Default camera seeded in database")

        enabled_cameras = [c for c in cameras if c.enabled]
        if enabled_cameras:
            from app.detection.worker import orchestrator
            for cam in enabled_cameras:
                await orchestrator.start_camera(cam)
            logger.info(f"Detection workers started for {len(enabled_cameras)} cameras")

    logger.info("Database initialized and seeded")
    yield
    logger.info("Shutting down...")
    from app.detection.worker import orchestrator
    await orchestrator.stop_all()
    logger.info("Detection workers stopped")


app = FastAPI(
    title="Poultry Monitoring API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_v1_router)
app.include_router(websocket_router)


@app.get("/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}
