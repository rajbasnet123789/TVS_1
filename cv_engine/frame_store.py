import json
import threading
import time
from pathlib import Path

from cv_engine.config import settings

_locks: dict[str, threading.Lock] = {}
_locks_lock = threading.Lock()

_metadata: dict[str, dict] = {}
_metadata_lock = threading.Lock()


def _get_lock(camera_id: str) -> threading.Lock:
    if camera_id not in _locks:
        with _locks_lock:
            if camera_id not in _locks:
                _locks[camera_id] = threading.Lock()
    return _locks[camera_id]


def _cache_dir() -> Path:
    d = Path(settings.STREAM_CACHE_DIR)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _raw_path(camera_id: str) -> Path:
    return _cache_dir() / f"{camera_id}.jpg"


def _annotated_path(camera_id: str) -> Path:
    return _cache_dir() / f"annotated_{camera_id}.jpg"


def publish(camera_id: str, jpeg_bytes: bytes) -> None:
    lock = _get_lock(camera_id)
    with lock:
        _raw_path(camera_id).write_bytes(jpeg_bytes)


def publish_annotated(camera_id: str, jpeg_bytes: bytes) -> None:
    lock = _get_lock(camera_id)
    with lock:
        _annotated_path(camera_id).write_bytes(jpeg_bytes)


def publish_metadata(camera_id: str, metadata: dict) -> None:
    with _metadata_lock:
        _metadata[camera_id] = metadata


def latest_bytes(camera_id: str, annotated: bool = False) -> bytes | None:
    lock = _get_lock(camera_id)
    with lock:
        path = _annotated_path(camera_id) if annotated else _raw_path(camera_id)
        if not path.exists():
            return None
        return path.read_bytes()


def latest_mtime(camera_id: str, annotated: bool = False) -> float:
    lock = _get_lock(camera_id)
    with lock:
        path = _annotated_path(camera_id) if annotated else _raw_path(camera_id)
        if not path.exists():
            return 0.0
        return path.stat().st_mtime


def latest_metadata(camera_id: str) -> dict | None:
    with _metadata_lock:
        return _metadata.get(camera_id)


def metadata_mtime(camera_id: str) -> float:
    with _metadata_lock:
        meta = _metadata.get(camera_id)
        if meta is None:
            return 0.0
        return meta.get("_mtime", 0.0)
