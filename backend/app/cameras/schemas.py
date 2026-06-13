from uuid import UUID
from datetime import datetime

from pydantic import BaseModel


class CameraCreate(BaseModel):
    name: str
    rtsp_url: str
    onvif_address: str | None = None
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


class CameraOut(BaseModel):
    id: UUID
    name: str
    rtsp_url: str
    onvif_address: str | None
    location: str | None
    zone: str | None
    status: str
    fps_target: int
    resolution_width: int
    resolution_height: int
    enabled: bool
    discovered_via_onvif: bool
    pos_x: int
    pos_y: int
    pos_z: int
    hls_url: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ONVIFChannel(BaseModel):
    channel: int
    profile_token: str
    rtsp_url: str | None = None
    name: str | None = None
    encoding: str | None = None
    resolution_width: int | None = None
    resolution_height: int | None = None


class ONVIFDevice(BaseModel):
    ip: str
    manufacturer: str | None = None
    model: str | None = None
    brand: str | None = None
    rtsp_url: str | None = None
    onvif_address: str | None = None
    device_service_url: str | None = None
    channels: list[ONVIFChannel] = []


class ONVIFScanRequest(BaseModel):
    subnet: str | None = None
    ip: str | None = None
    username: str | None = None
    password: str | None = None
