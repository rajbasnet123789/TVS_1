from fastapi import APIRouter

from app.alerts.router import router as alerts_router
from app.analytics.router import router as analytics_router
from app.auth.router import router as auth_router
from app.cameras.router import router as cameras_router
from app.coops.router import router as coops_router
from app.chickens.router import router as chickens_router
from app.detection.router import router as detection_router, global_router as detection_global_router
from app.environment.router import router as environment_router
from app.farms.router import router as farms_router
from app.frigate.router import router as frigate_router
from app.health.router import router as health_router
from app.media.router import router as media_router
from app.nvr.router import router as nvr_router
from app.websocket.router import router as ws_router
from app.api.v1.intruders import router as intruders_router

router = APIRouter(prefix="/v1")
router.include_router(alerts_router)
router.include_router(analytics_router)
router.include_router(auth_router)
router.include_router(cameras_router)
router.include_router(coops_router)
router.include_router(chickens_router)
router.include_router(environment_router)
router.include_router(farms_router)
router.include_router(frigate_router)
router.include_router(health_router)
router.include_router(media_router)
router.include_router(nvr_router)
router.include_router(detection_router)
router.include_router(detection_global_router)
router.include_router(intruders_router)

websocket_router = ws_router
