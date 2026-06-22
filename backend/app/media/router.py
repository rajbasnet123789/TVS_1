import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile, status

from app.auth.deps import get_farm_id, require_permission
from app.auth.models import User
from app.media.schemas import MediaInfo, MediaListResponse, MediaUploadResponse
from app.media.client import delete_object, get_object, list_objects, put_object
from app.rate_limit import limiter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/media", tags=["media"])


def validate_media_key(key: str) -> None:
    if not key:
        return
    if ".." in key or "\\" in key or key.startswith("/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid path: path traversal patterns or absolute paths are not allowed"
        )


@router.post("/upload", response_model=MediaUploadResponse)
@limiter.limit("20/minute")
async def upload_media(
    request: Request,
    file: UploadFile,
    prefix: str = Query(
        "",
        description="Optional subdirectory within farm path",
        pattern=r"^([a-zA-Z0-9_-]+(/[a-zA-Z0-9_-]+)*)?$"
    ),
    user: User = Depends(require_permission("cameras:write")),
    farm_id: str | None = Depends(get_farm_id),
):
    if not farm_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="farm_id required")
    validate_media_key(prefix)
    if not file.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No filename provided")
    validate_media_key(file.filename)
    
    MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB
    data = await file.read(MAX_FILE_SIZE + 1)
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty file")
    if len(data) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File too large (maximum size is 100MB)"
        )
    content_type = file.content_type or "application/octet-stream"
    key = f"{prefix}/{file.filename}" if prefix else file.filename
    path = await put_object(farm_id, key, data, content_type)
    return MediaUploadResponse(key=path, url=f"/api/v1/media/download/{path}")


@router.get("/download/{key:path}")
async def download_media(
    key: str,
    user: User = Depends(require_permission("cameras:read")),
    farm_id: str | None = Depends(get_farm_id),
):
    if not farm_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="farm_id required")
    validate_media_key(key)
    data = await get_object(farm_id, key)
    if data is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    from fastapi.responses import Response
    ext_to_mime = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".mp4": "video/mp4",
        ".json": "application/json",
    }
    ext = next((e for e in ext_to_mime if key.lower().endswith(e)), None)
    media_type = ext_to_mime.get(ext) if ext else "application/octet-stream"
    return Response(content=data, media_type=media_type)


@router.delete("/delete/{key:path}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("20/minute")
async def delete_media(
    key: str,
    request: Request,
    user: User = Depends(require_permission("cameras:write")),
    farm_id: str | None = Depends(get_farm_id),
):
    if not farm_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="farm_id required")
    validate_media_key(key)
    deleted = await delete_object(farm_id, key)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")


@router.get("/list", response_model=MediaListResponse)
async def list_media(
    prefix: str = Query(
        "",
        description="Optional subdirectory within farm path",
        pattern=r"^([a-zA-Z0-9_-]+(/[a-zA-Z0-9_-]+)*)?$"
    ),
    user: User = Depends(require_permission("cameras:read")),
    farm_id: str | None = Depends(get_farm_id),
):
    if not farm_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="farm_id required")
    validate_media_key(prefix)
    objects = await list_objects(farm_id, prefix=prefix)
    return MediaListResponse(
        objects=[MediaInfo(key=o, url=f"/api/v1/media/download/{o}") for o in objects]
    )
