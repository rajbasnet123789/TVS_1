from datetime import datetime

from pydantic import BaseModel


class EnvironmentSnapshot(BaseModel):
    status: str
    message: str
    temperature: float | None = None
    ammonia: float | None = None
    humidity: float | None = None
    wind_speed: float | None = None
    recorded_at: datetime | None = None


class EnvironmentHistoryPoint(BaseModel):
    time: str
    temperature: float | None = None
    ammonia: float | None = None
    humidity: float | None = None


class EnvironmentHistory(BaseModel):
    status: str
    series: list[EnvironmentHistoryPoint]
