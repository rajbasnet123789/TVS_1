from uuid import UUID
from datetime import datetime

from pydantic import BaseModel


class CameraCreate(BaseModel):
    name: str
    rtsp_url: str
    location: str | None = None
    zone: str | None = None
    fps_target: int = 5
    resolution_width: int = 1920
    resolution_height: int = 1080
    username: str | None = None
    password: str | None = None
    pos_x: int = 0
    pos_y: int = 0
    pos_z: int = 0
    roi: list[list[float]] | None = None
    coop_id: str | None = None
    snapshot_url: str | None = None


class CameraUpdate(BaseModel):
    name: str | None = None
    rtsp_url: str | None = None
    location: str | None = None
    zone: str | None = None
    fps_target: int | None = None
    username: str | None = None
    password: str | None = None
    enabled: bool | None = None
    pos_x: int | None = None
    pos_y: int | None = None
    pos_z: int | None = None
    roi: list[list[float]] | None = None
    coop_id: str | None = None
    snapshot_url: str | None = None


class AssignCoopRequest(BaseModel):
    coop_id: str | None = None  # null to unassign


class DiscoveredDevice(BaseModel):
    name: str
    device_url: str
    ip: str
    xaddrs: str
    types: str
    scopes: str


class ScanStatus(BaseModel):
    scanning: bool
    progress: float | None = None
    devices_found: int = 0
    error: str | None = None


class CameraOut(BaseModel):
    id: UUID
    name: str
    rtsp_url: str
    location: str | None
    zone: str | None
    status: str
    fps_target: int
    resolution_width: int
    resolution_height: int
    enabled: bool
    pos_x: int
    pos_y: int
    pos_z: int
    coop_id: UUID | None = None
    snapshot_url: str | None = None
    roi: list[list[float]] | None = None
    hls_url: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
