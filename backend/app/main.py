import logging
import os
import uuid

# Force OpenCV/FFmpeg to use TCP for RTSP streams to avoid packet corruption/timeout errors
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"

from contextlib import asynccontextmanager
from contextvars import ContextVar

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.api.v1.router import router as api_v1_router
from app.api.v1.router import websocket_router
from app.config import settings
from app.database import init_db
from app.auth.service import seed_default_farm, seed_roles, seed_super_admin
from app.rate_limit import limiter

# Import all models to register them on Base.metadata for database initialization
import app.auth.models
import app.farms.models
import app.chickens.models
import app.cameras.models
import app.alerts.models

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


class RequestIDFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        if not hasattr(record, "request_id"):
            record.request_id = request_id_var.get()
        return super().format(record)


handler = logging.StreamHandler()
handler.setFormatter(
    RequestIDFormatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s  [request_id=%(request_id)s]"
    )
)

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    handlers=[handler],
)
logger = logging.getLogger(__name__)


async def register_existing_cameras_in_frigate():
    from app.database import async_session
    from sqlalchemy import select
    from app.cameras.models import Camera
    from app.security import decrypt_camera_password
    from app.frigate.config_manager import add_camera_to_frigate
    from app.frigate.schemas import FrigateCameraConfig
    from app.utils import retry_async
    
    async with async_session() as db:
        result = await db.execute(select(Camera))
        cameras = result.scalars().all()
        for camera in cameras:
            try:
                plain = decrypt_camera_password(camera.password_hash) if camera.password_hash else None
                cfg = FrigateCameraConfig(
                    name=camera.name,
                    rtsp_url=camera.rtsp_url,
                    username=camera.username or None,
                    password=plain,
                    enabled=camera.enabled,
                )
                await retry_async(add_camera_to_frigate, cfg, max_retries=3, delay=1.0, backoff=2.0)
                logger.info(f"Registered camera {camera.name} in Frigate config")
            except Exception as e:
                logger.warning(f"Failed to register camera {camera.name} in Frigate: {e}")


def assert_single_worker():
    """
    Enforce that the current application instance runs with exactly one worker process
    (per-instance check, not a global single-instance enforcement).
    This is required because the application relies on process-local states
    for network scanning, camera detection workers, and local camera streams.
    """
    import os
    import sys
    
    # 1. Check common environment variables specifying workers
    for env_var in ["WEB_CONCURRENCY", "WORKERS", "UVICORN_WORKERS"]:
        val = os.environ.get(env_var)
        if val and val.isdigit() and int(val) > 1:
            raise AssertionError(
                f"Multiple workers detected via environment variable {env_var}={val}. "
                "This application requires exactly one worker due to process-local state."
            )
            
    # 2. Check sys.argv for workers config
    args = sys.argv
    for i, arg in enumerate(args):
        if arg in ("--workers", "-w"):
            if i + 1 < len(args) and args[i + 1].isdigit() and int(args[i + 1]) > 1:
                raise AssertionError(
                    f"Multiple workers detected via command line argument '{arg} {args[i+1]}'. "
                    "This application requires exactly one worker due to process-local state."
                )

    # 3. Check process tree using psutil
    try:
        import psutil
        current_process = psutil.Process(os.getpid())
        parent = current_process.parent()
        if parent:
            # Under uvicorn/gunicorn, if there are multiple workers, the parent is the master process.
            parent_cmdline = parent.cmdline()
            for i, arg in enumerate(parent_cmdline):
                if arg in ("--workers", "-w"):
                    if i + 1 < len(parent_cmdline) and parent_cmdline[i + 1].isdigit() and int(parent_cmdline[i + 1]) > 1:
                        raise AssertionError(
                            "Multiple workers detected in parent process command line. "
                            "This application requires exactly one worker due to process-local state."
                        )
    except Exception:
        pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up...")
    assert_single_worker()
    await init_db()
    from app.database import async_session
    async with async_session() as db:
        await seed_roles(db)
        await seed_default_farm(db)
        await seed_super_admin(db)
        await db.commit()

    # Register all cameras in Frigate config in case of Frigate restart
    await register_existing_cameras_in_frigate()

    # Load health classification model
    from app.detection.detector import detector
    await detector.load_health()
    logger.info("Health classification model loaded")

    # Load Intruder detector face recognition models
    from app.detection.intruder import intruder_detector
    try:
        intruder_detector.load()
        logger.info("Intruder face recognition detector loaded")
    except Exception as e:
        logger.warning(f"Intruder face recognition detector load failed: {e}")

    # Initialize MCMT global tracker (loaded by subscriber and detection router)
    from app.detection.mcmt_singleton import init_mcmt_tracker
    await init_mcmt_tracker()
    logger.info("MCMT GlobalTracker initialized")

    # Start Frigate MQTT subscriber
    from app.frigate.subscriber import subscriber
    await subscriber.start()
    logger.info("Frigate MQTT subscriber started")

    from app.alerts.rules import alert_evaluator
    await alert_evaluator.start()
    logger.info("Alert rule evaluator started")

    if settings.sentry_dsn:
        import sentry_sdk
        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            environment=settings.environment,
            traces_sample_rate=0.1,
        )
        logger.info("Sentry initialized")
    from app.media.client import get_media_root
    root = get_media_root()
    logger.info("Media root: %s", root)

    if settings.nvr_host and settings.nvr_username and settings.nvr_password:
        from app.nvr.client import init_nvr_client
        await init_nvr_client(settings.nvr_host, settings.nvr_username, settings.nvr_password)
        logger.info("NVR client initialized (%s)", settings.nvr_host)
    else:
        logger.info("NVR not configured — NVR-dependent endpoints will return 503")

    logger.info("Database initialized and seeded")
    yield
    logger.info("Shutting down...")
    from app.cameras.router import cancel_active_scan
    await cancel_active_scan()
    logger.info("Active ONVIF scans cancelled")
    await alert_evaluator.stop()
    logger.info("Alert rule evaluator stopped")
    from app.nvr.client import close_nvr_client
    await close_nvr_client()
    logger.info("NVR client closed")
    from app.frigate.subscriber import subscriber
    await subscriber.stop()
    logger.info("Frigate subscriber stopped")
    from app.frigate.client import close_client
    await close_client()
    logger.info("Frigate HTTP client closed")
    from app.auth.service import close_redis
    await close_redis()
    logger.info("Redis client closed")


app = FastAPI(
    title="Coop Vision API",
    version="0.1.0",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Requested-With", "X-Farm-ID"],
)


@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    token = request_id_var.set(request_id)
    try:
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response
    finally:
        request_id_var.reset(token)


app.include_router(api_v1_router)
app.include_router(websocket_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
