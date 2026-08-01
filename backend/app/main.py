import logging
import os
import uuid

os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"

from contextlib import asynccontextmanager
from contextvars import ContextVar

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

import app.alerts.models
import app.auth.models
import app.cameras.models
import app.chickens.models
import app.farms.models
from app.api.v1.router import router as api_v1_router
from app.api.v1.router import websocket_router
from app.auth.service import seed_default_farm, seed_roles, seed_super_admin
from app.config import settings
from app.database import init_db
from app.rate_limit import limiter

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


def assert_single_worker():
    import sys
    for env_var in ["WEB_CONCURRENCY", "WORKERS", "UVICORN_WORKERS"]:
        val = os.environ.get(env_var)
        if val and val.isdigit() and int(val) > 1:
            raise AssertionError(
                f"Multiple workers detected via environment variable {env_var}={val}. "
                "This application requires exactly one worker due to process-local state."
            )
    args = sys.argv
    for i, arg in enumerate(args):
        if arg in ("--workers", "-w") and i + 1 < len(args) and args[i + 1].isdigit() and int(args[i + 1]) > 1:
                raise AssertionError(
                    f"Multiple workers detected via command line argument '{arg} {args[i+1]}'. "
                    "This application requires exactly one worker due to process-local state."
                )
    try:
        import psutil
        current_process = psutil.Process(os.getpid())
        parent = current_process.parent()
        if parent:
            parent_cmdline = parent.cmdline()
            for i, arg in enumerate(parent_cmdline):
                if arg in ("--workers", "-w") and i + 1 < len(parent_cmdline) and parent_cmdline[i + 1].isdigit() and int(parent_cmdline[i + 1]) > 1:
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

    if settings.nvr_host:
        from app.nvr.client import init_nvr_client
        try:
            await init_nvr_client(settings.nvr_host, settings.nvr_username, settings.nvr_password)
            logger.info("NVR client initialized: %s", settings.nvr_host)
        except Exception as e:
            logger.warning("NVR client init failed: %s", e)

    logger.info("Database initialized and seeded")
    yield
    logger.info("Shutting down...")
    from app.cameras.router import cancel_active_scan
    await cancel_active_scan()
    logger.info("Active ONVIF scans cancelled")
    from app.nvr.client import close_nvr_client
    await close_nvr_client()
    logger.info("NVR client closed")
    await alert_evaluator.stop()
    logger.info("Alert rule evaluator stopped")
    from app.auth.service import close_redis
    await close_redis()
    logger.info("Redis client closed")


app = FastAPI(
    title="Coop Vision API",
    version="0.2.0",
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
