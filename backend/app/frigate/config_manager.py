import copy
import logging
from typing import Optional

import yaml

from app.frigate.schemas import FrigateCameraConfig

logger = logging.getLogger(__name__)


def build_camera_config(cam: FrigateCameraConfig) -> dict:
    if cam.rtsp_url.startswith("rtsp://") and cam.username and cam.password:
        import urllib.parse
        parsed = urllib.parse.urlparse(cam.rtsp_url)
        netloc = parsed.netloc
        if "@" in netloc:
            host = netloc.split("@", 1)[1]
        else:
            host = netloc
        new_netloc = f"{cam.username}:{cam.password}@{host}"
        parsed = parsed._replace(netloc=new_netloc)
        rtsp_url = urllib.parse.urlunparse(parsed)
    else:
        rtsp_url = cam.rtsp_url

    entry: dict = {
        "name": cam.name,
        "enabled": cam.enabled,
        "ffmpeg": {
            "inputs": [
                {
                    "path": rtsp_url,
                    "roles": ["record", "detect"],
                    "global_args": "-re",
                    "input_args": "-avoid_negative_ts make_zero -fflags nobuffer -flags low_delay -strict experimental -analyzeduration 1000M -probesize 1000M",
                }
            ]
        },
        "detect": {
            "enabled": cam.detect_enabled,
            "width": 1280,
            "height": 720,
            "fps": 5,
        },
        "record": {
            "enabled": True,
            "retain": {"days": cam.record_days},
        },
        "snapshots": {
            "enabled": cam.snapshots_enabled,
            "timestamp": True,
            "bounding_box": True,
            "retain": {"default": cam.record_days},
        },
        "objects": {
            "track": cam.objects_to_track if cam.objects_to_track else ["bird"],
        },
        "motion": {"mask": []},
        "zones": {z: {"coordinates": []} for z in cam.zones} if cam.zones else {},
    }

    if cam.rtsp_url.startswith("rtsp://"):
        default_args = entry["ffmpeg"]["inputs"][0]["input_args"]
        entry["ffmpeg"]["inputs"][0]["input_args"] = f"-rtsp_transport tcp {default_args}"

    return entry


def build_full_config(camera_configs: list[dict], existing_config: Optional[dict] = None) -> dict:
    base = {
        "mqtt": {"host": "mosquitto", "port": 1883, "topic_prefix": "frigate", "client_id": "frigate"},
        "database": {"path": "/config/frigate.db"},
        "cameras": {},
    }

    if existing_config:
        base = copy.deepcopy(existing_config)
        base.setdefault("cameras", {})

    for cfg in camera_configs:
        name = cfg.pop("name", "unnamed")
        base["cameras"][name] = cfg

    return base


def generate_camera_yaml(cam: FrigateCameraConfig) -> str:
    config = build_camera_config(cam)
    config["name"] = cam.name
    return yaml.dump({cam.name: config}, default_flow_style=False, sort_keys=False)


async def add_camera_to_frigate(cam: FrigateCameraConfig):
    from app.frigate.client import get_frigate_config, save_frigate_config

    existing = await get_frigate_config()
    cameras = existing.setdefault("cameras", {})
    cameras[cam.name] = build_camera_config(cam)

    await save_frigate_config(existing)


async def remove_camera_from_frigate(camera_name: str):
    from app.frigate.client import get_frigate_config, save_frigate_config

    existing = await get_frigate_config()
    cameras = existing.get("cameras", {})
    if camera_name in cameras:
        del cameras[camera_name]
    await save_frigate_config(existing)


async def update_camera_in_frigate(cam: FrigateCameraConfig):
    from app.frigate.client import get_frigate_config, save_frigate_config

    existing = await get_frigate_config()
    cameras = existing.setdefault("cameras", {})
    cameras[cam.name] = build_camera_config(cam)
    await save_frigate_config(existing)
