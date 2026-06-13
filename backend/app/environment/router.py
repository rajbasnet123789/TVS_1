from fastapi import APIRouter, Depends

from app.auth.deps import require_permission
from app.auth.models import User
from app.environment.schemas import EnvironmentHistory, EnvironmentSnapshot

router = APIRouter(prefix="/environment", tags=["environment"])


@router.get("", response_model=EnvironmentSnapshot)
async def get_current_environment(
    user: User = Depends(require_permission("dashboard:read")),
):
    return EnvironmentSnapshot(
        status="no_data",
        message="Connect IoT gateway to receive telemetry",
    )


@router.get("/history", response_model=EnvironmentHistory)
async def get_environment_history(
    user: User = Depends(require_permission("dashboard:read")),
):
    return EnvironmentHistory(status="no_data", series=[])
