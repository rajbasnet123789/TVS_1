from datetime import datetime

from pydantic import BaseModel


class HealthRecord(BaseModel):
    camera_id: str
    track_id: int | None = None
    health_class: str
    health_score: float
    health_confidence: float
    timestamp: datetime


class HealthSummary(BaseModel):
    camera_id: str | None = None
    total_records: int = 0
    avg_health_score: float = 0
    min_health_score: float | None = None
    max_health_score: float | None = None
    class_distribution: dict[str, int] = {}


class TimeSeriesPoint(BaseModel):
    time: datetime
    value: float
