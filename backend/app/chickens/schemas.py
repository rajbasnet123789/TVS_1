from uuid import UUID
from datetime import datetime

from pydantic import BaseModel


class ChickenCreate(BaseModel):
    chicken_id: int
    name: str | None = None
    breed: str | None = None
    notes: str | None = None
    global_id: int | None = None


class ChickenUpdate(BaseModel):
    name: str | None = None
    breed: str | None = None
    status: str | None = None
    notes: str | None = None
    global_id: int | None = None


class ChickenOut(BaseModel):
    id: UUID
    chicken_id: int
    name: str | None
    breed: str | None
    status: str
    notes: str | None
    global_id: int | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DetectedChicken(BaseModel):
    track_id: int
    detections: int
    avg_confidence: float
    last_seen: datetime
    first_seen: datetime
    cameras: list[str]
    status: str  # active | inactive
