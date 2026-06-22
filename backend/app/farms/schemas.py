from uuid import UUID
from datetime import datetime

from pydantic import BaseModel


class FarmCreate(BaseModel):
    name: str
    location: str | None = None
    slug: str | None = None


class FarmUpdate(BaseModel):
    name: str | None = None
    location: str | None = None
    slug: str | None = None
    settings: dict | None = None
    is_active: bool | None = None


class FarmOut(BaseModel):
    id: UUID
    name: str
    location: str | None
    slug: str
    settings: dict
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
