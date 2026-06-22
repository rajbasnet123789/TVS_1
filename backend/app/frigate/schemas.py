from pydantic import BaseModel


class FrigateEvent(BaseModel):
    type: str
    before: dict | None = None
    after: dict | None = None


class FrigateCameraConfig(BaseModel):
    name: str
    rtsp_url: str
    username: str | None = None
    password: str | None = None
    enabled: bool = True
    record_days: int = 7
    snapshots_enabled: bool = True
    detect_enabled: bool = True
    zones: list[str] = []
    objects_to_track: list[str] = ["bird"]


class FrigateConfigEntry(BaseModel):
    enabled: bool = True
    ffmpeg: dict | None = None
    detect: dict = {"enabled": True, "width": 1280, "height": 720, "fps": 5}
    record: dict = {"enabled": True, "retain": {"days": 7}}
    snapshots: dict = {"enabled": True, "timestamp": True, "bounding_box": True, "retain": {"default": 7}}
    objects: dict = {"track": ["bird"]}
    motion: dict = {"mask": []}
