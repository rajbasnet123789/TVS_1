import logging
import os
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)

MEDIA_ROOT: Path | None = None


def get_media_root() -> Path:
    global MEDIA_ROOT
    if MEDIA_ROOT is None:
        MEDIA_ROOT = Path(settings.media_root)
        MEDIA_ROOT.mkdir(parents=True, exist_ok=True)
    return MEDIA_ROOT


def _farm_dir(farm_id: str) -> Path:
    if not farm_id:
        raise ValueError("farm_id is required for media isolation")
    d = get_media_root() / "farms" / farm_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def _resolve(farm_id: str, key: str) -> Path:
    key = key.lstrip("/")
    path = _farm_dir(farm_id) / key
    path = path.resolve()
    farm_dir_resolved = _farm_dir(farm_id).resolve()
    try:
        path.relative_to(farm_dir_resolved)
    except ValueError:
        raise ValueError("Path traversal detected")
    return path


async def put_object(
    farm_id: str,
    key: str,
    data: bytes,
    content_type: str | None = None,
) -> str:
    path = _resolve(farm_id, key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    logger.info(f"Wrote {len(data)} bytes to {path}")
    return key.lstrip("/")


async def get_object(farm_id: str, key: str) -> bytes | None:
    path = _resolve(farm_id, key)
    if not path.exists():
        return None
    return path.read_bytes()


async def delete_object(farm_id: str, key: str) -> bool:
    path = _resolve(farm_id, key)
    if not path.exists():
        return False
    path.unlink()
    logger.info(f"Deleted {path}")
    parent = path.parent
    while parent != _farm_dir(farm_id) and parent != get_media_root():
        if any(parent.iterdir()):
            break
        parent.rmdir()
        parent = parent.parent
    return True


async def list_objects(farm_id: str, prefix: str = "") -> list[str]:
    base = _farm_dir(farm_id)
    search_dir = base / prefix.lstrip("/") if prefix else base
    if not search_dir.exists():
        return []
    keys: list[str] = []
    for p in search_dir.rglob("*"):
        if p.is_file():
            rel = p.relative_to(base)
            keys.append(str(rel.as_posix()))
    keys.sort()
    return keys
