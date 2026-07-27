"""Pydantic schemas for XMEye / DVRIP API endpoints."""
from pydantic import BaseModel, Field


class XMEyeChannelInfo(BaseModel):
    """A single channel on an XMEye NVR."""
    channel: int = Field(..., description="1-based channel number")
    name: str = Field(..., description="Channel label (e.g. 'Channel 1' or custom NVR label)")
    rtsp_url_main: str = Field(..., description="Main stream RTSP URL (HD)")
    rtsp_url_sub: str = Field(..., description="Sub stream RTSP URL (SD)")
    rtsp_url_main_b: str = Field(..., description="Main stream RTSP URL — alternate format B")
    rtsp_url_sub_b: str = Field(..., description="Sub stream RTSP URL — alternate format B")


class XMEyeDiscoveredDevice(BaseModel):
    """A device returned by the XMEye UDP LAN scan."""
    ip: str
    tcp_port: int = 34567
    http_port: int = 80
    device_name: str = ""
    device_type: str = ""       # IPC / DVR / NVR / Unknown
    serial_no: str = ""
    mac: str = ""
    channel_count: int = 1
    software_version: str = ""
    build_date: str = ""


class XMEyeScanResponse(BaseModel):
    """Response from POST /xmeye/scan."""
    devices: list[XMEyeDiscoveredDevice]
    count: int


class XMEyeConnectRequest(BaseModel):
    """Request body for POST /xmeye/connect — validate credentials and list channels."""
    ip: str = Field(..., description="Camera or NVR IP address")
    port: int = Field(34567, description="DVRIP TCP port (usually 34567)")
    rtsp_port: int = Field(554, description="RTSP port (usually 554)")
    username: str = Field("admin", description="Login username")
    password: str = Field("", description="Login password (plaintext)")
    channel_count: int | None = Field(
        None,
        description=(
            "Override channel count (use when already known from discovery). "
            "If omitted, the server will use the channel count from the DVRIP login response."
        ),
    )


class XMEyeConnectResponse(BaseModel):
    """Response from POST /xmeye/connect."""
    success: bool
    session_id: str = ""
    device_type: str = ""
    channels: list[XMEyeChannelInfo] = []
    error: str | None = None


class XMEyeAddChannelsRequest(BaseModel):
    """Request body for POST /xmeye/add — add selected channels as cameras."""
    ip: str
    username: str
    password: str
    rtsp_port: int = 554
    channels: list[int] = Field(..., description="List of 1-based channel numbers to add")
    location: str | None = None
    zone: str | None = None
    fps_target: int = 5
    use_substream: bool = Field(False, description="Use sub stream (SD) instead of main (HD)")
    rtsp_format: str = Field("A", description="RTSP URL format: 'A' (legacy XMEye) or 'B' (channel path)")
