import threading

_frames: dict[str, bytes] = {}
_locks: dict[str, threading.Lock] = {}
_locks_lock = threading.Lock()


def _get_lock(camera_id: str) -> threading.Lock:
    if camera_id not in _locks:
        with _locks_lock:
            if camera_id not in _locks:
                _locks[camera_id] = threading.Lock()
    return _locks[camera_id]


def publish(camera_id: str, jpeg_bytes: bytes) -> None:
    """Store the latest JPEG frame in memory.

    The ffmpeg capture thread and the inference loop run in the same worker
    process, so a plain in-memory dict replaces the previous per-frame disk
    write + read (which was 25 I/O ops/sec/camera).
    """
    lock = _get_lock(camera_id)
    with lock:
        if jpeg_bytes:
            _frames[camera_id] = jpeg_bytes
        else:
            _frames.pop(camera_id, None)


def latest_bytes(camera_id: str) -> bytes | None:
    lock = _get_lock(camera_id)
    with lock:
        return _frames.get(camera_id)


def latest_mtime(camera_id: str) -> float:
    lock = _get_lock(camera_id)
    with lock:
        return 1.0 if camera_id in _frames else 0.0
