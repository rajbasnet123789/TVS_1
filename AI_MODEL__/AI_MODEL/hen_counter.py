"""
HenCounter: Wraps ZoneBasedCounter with detection tracking and trajectory storage.

Provides the interface expected by main.py while using ZoneBasedCounter's
line-crossing counting underneath.
"""

import time
import numpy as np
from dataclasses import dataclass, field
from typing import Optional

from transformers.zone_counter import ZoneBasedCounter


@dataclass
class TrackedHen:
    global_id: int
    track_id: int
    centroid: tuple[float, float]
    bbox: dict
    confidence: float
    zone: str
    first_seen: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    frames_visible: int = 1


class HenCounter:
    def __init__(self, frame_width: int = 640, frame_height: int = 480):
        self.frame_width = frame_width
        self.frame_height = frame_height
        self.counter = ZoneBasedCounter(frame_width, frame_height)
        self.counter.add_default_lines()
        self._active_hens: dict[int, TrackedHen] = {}
        self._all_hens: dict[int, TrackedHen] = {}
        self._trajectories: dict[int, list[tuple[float, float]]] = {}
        self._frame_count = 0

    def process_frame(
        self,
        detections: list[dict],
        track_ids: list[Optional[int]],
    ) -> dict:
        # Convert bbox dict {"x","y","w","h"} to tuple (x1,y1,x2,y2) for ZoneBasedCounter
        counter_dets = []
        for det in detections:
            b = det["bbox"]
            counter_dets.append({
                "bbox": (b["x"], b["y"], b["x"] + b["w"], b["y"] + b["h"]),
                "confidence": det["confidence"],
                "class_id": det.get("class_id", 0),
                "class_name": det.get("class_name", ""),
            })
        self.counter.process_frame(counter_dets, track_ids)

        self._active_hens.clear()
        for det, tid in zip(detections, track_ids):
            if tid is None:
                continue

            cx = det["bbox"]["x"] + det["bbox"]["w"] / 2
            cy = det["bbox"]["y"] + det["bbox"]["h"] / 2
            centroid = (cx, cy)

            gid = det.get("global_id", tid)
            hen = TrackedHen(
                global_id=gid,
                track_id=tid,
                centroid=centroid,
                bbox=det["bbox"],
                confidence=det["confidence"],
                zone="",
            )
            if gid in self._all_hens:
                hen.first_seen = self._all_hens[gid].first_seen
                hen.frames_visible = self._all_hens[gid].frames_visible + 1
            self._active_hens[tid] = hen
            self._all_hens[gid] = hen

            if tid not in self._trajectories:
                self._trajectories[tid] = []
            self._trajectories[tid].append(centroid)
            if len(self._trajectories[tid]) > 60:
                self._trajectories[tid].pop(0)

        self._frame_count += 1

        zone_counts = {
            "net_count": self.counter.get_net_count(),
        }

        return {
            "detections": [
                {
                    "bbox": hen.bbox,
                    "confidence": hen.confidence,
                    "global_id": hen.global_id,
                    "track_id": hen.track_id,
                    "zone": hen.zone,
                }
                for hen in self._active_hens.values()
            ],
            "current_count": len(self._active_hens),
            "unique_count": len(self._all_hens),
            "total_seen": len(self._all_hens),
            "zone_counts": zone_counts,
        }

    def get_unique_count(self) -> int:
        return len(self._all_hens)

    def get_current_visible(self) -> int:
        return len(self._active_hens)

    def get_total_seen(self) -> int:
        return len(self._all_hens)

    def get_zone_counts(self) -> dict[str, int]:
        return {"net_count": self.counter.get_net_count()}

    def get_trajectories(self) -> dict[int, list[tuple[float, float]]]:
        return self._trajectories

    def reset(self):
        self.counter.reset()
        self._active_hens.clear()
        self._all_hens.clear()
        self._trajectories.clear()
        self._frame_count = 0
