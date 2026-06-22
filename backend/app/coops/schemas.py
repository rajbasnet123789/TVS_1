from uuid import UUID
from datetime import datetime

from pydantic import BaseModel

from app.cameras.schemas import CameraOut


class CoopCreate(BaseModel):
    name: str
    sort_order: int = 0


class CoopUpdate(BaseModel):
    name: str | None = None
    sort_order: int | None = None


class CoopOut(BaseModel):
    id: UUID
    name: str
    sort_order: int
    created_at: datetime
    cameras: list[CameraOut] = []

    model_config = {"from_attributes": True}
