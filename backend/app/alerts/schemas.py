from datetime import datetime

from pydantic import BaseModel


class AlertCreate(BaseModel):
    camera_id: str | None = None
    chicken_id: str | None = None
    track_id: str | None = None
    type: str
    severity: int = 0
    message: str


class AlertOut(BaseModel):
    id: str
    camera_id: str | None = None
    chicken_id: str | None = None
    track_id: str | None = None
    type: str
    severity: int
    message: str
    created_at: datetime
    acknowledged_at: datetime | None = None

    model_config = {"from_attributes": True}


class AlertRuleOut(BaseModel):
    id: str
    name: str
    metric: str
    operator: str
    threshold: int
    duration_minutes: int
    severity: int
    enabled: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class AlertRuleUpdate(BaseModel):
    name: str | None = None
    metric: str | None = None
    operator: str | None = None
    threshold: int | None = None
    duration_minutes: int | None = None
    severity: int | None = None
    enabled: bool | None = None


class AlertAcknowledge(BaseModel):
    pass
