from datetime import datetime
from pydantic import BaseModel


class BBox(BaseModel):
    x: float
    y: float
    w: float
    h: float


class Detection(BaseModel):
    camera_id: str
    timestamp: datetime
    class_id: int
    class_name: str
    confidence: float
    bbox: BBox
    track_id: int | None = None


class DetectionEvent(BaseModel):
    type: str = "detection"
    camera_id: str
    timestamp: str
    detections: list[Detection]


class DetectionStats(BaseModel):
    total_detections: int = 0
    unique_chickens: int = 0
    detections_per_minute: float = 0
    active_cameras: int = 0


class TimeSeriesPoint(BaseModel):
    time: datetime
    value: float


class DetectionHistory(BaseModel):
    camera_id: str
    window: str
    detection_series: list[TimeSeriesPoint]
    headcount_series: list[TimeSeriesPoint]


class DetectionSummary(BaseModel):
    total_detections: int = 0
    unique_chickens: int = 0
    peak_head_count: int = 0
    avg_confidence: float = 0
    active_minutes: int = 0
    detections_per_hour: float = 0
