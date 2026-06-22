from pydantic import BaseModel


class MediaUploadResponse(BaseModel):
    key: str
    url: str


class MediaInfo(BaseModel):
    key: str
    url: str


class MediaListResponse(BaseModel):
    objects: list[MediaInfo]
