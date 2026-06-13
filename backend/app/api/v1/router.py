from fastapi import APIRouter

from app.auth.router import router as auth_router
from app.cameras.router import router as cameras_router
from app.chickens.router import router as chickens_router
from app.detection.router import router as detection_router, global_router as detection_global_router
from app.environment.router import router as environment_router
from app.websocket.router import router as ws_router

router = APIRouter(prefix="/v1")
router.include_router(auth_router)
router.include_router(cameras_router)
router.include_router(chickens_router)
router.include_router(environment_router)
router.include_router(detection_router)
router.include_router(detection_global_router)

websocket_router = ws_router
