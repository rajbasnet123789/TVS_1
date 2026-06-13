"""
HenCounter: Orchestrates YOLOv8 detection + BoT-SORT (OSNet ReID) + zone-based counting.

BoT-SORT maintains frame-to-frame track IDs using both motion (Kalman filter)
and appearance embeddings (OSNet), providing robust identity tracking even when
hens occlude each other. This module adds zone counting and global ID persistence
via spatial-temporal proximity as a secondary fallback.
"""

import time
import numpy as np
from dataclasses import dataclass, field
from typing import Optional

from reid import ZoneBasedCounter


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
        self.counter = ZoneBasedCounter(frame_width, frame_height)
        self.counter.add_default_zones()
        self._active_hens: dict[int, TrackedHen] = {}
        self._all_hens: dict[int, TrackedHen] = {}
        self._frame_count = 0

    def process_frame(
        self,
        detections: list[dict],
        track_ids: list[Optional[int]],
    ) -> dict:
        result = self.counter.process_frame(detections, track_ids)

        self._active_hens.clear()
        for det in result["detections"]:
            gid = det["global_id"]
            hen = TrackedHen(
                global_id=gid,
                track_id=det["track_id"],
                centroid=(
                    det["bbox"]["x"] + det["bbox"]["w"] / 2,
                    det["bbox"]["y"] + det["bbox"]["h"] / 2,
                ),
                bbox=det["bbox"],
                confidence=det["confidence"],
                zone=det.get("zone", ""),
            )
            if gid in self._all_hens:
                hen.first_seen = self._all_hens[gid].first_seen
                hen.frames_visible = self._all_hens[gid].frames_visible + 1
            self._active_hens[det["track_id"]] = hen
            self._all_hens[gid] = hen

        self._frame_count += 1

        return {
            "detections": result["detections"],
            "current_count": result["current_count"],
            "unique_count": result["unique_count"],
            "total_seen": result["total_seen"],
            "zone_counts": result["zone_counts"],
        }

    def get_unique_count(self) -> int:
        return self.counter.get_unique_count()

    def get_current_visible(self) -> int:
        return self.counter.get_current_visible()

    def get_total_seen(self) -> int:
        return self.counter.get_total_seen()

    def get_zone_counts(self) -> dict[str, int]:
        return self.counter.get_zone_counts()

    def get_trajectories(self) -> dict[int, list[tuple[float, float]]]:
        return self.counter.get_trajectories()

    def reset(self):
        self.counter.reset()
        self._active_hens.clear()
        self._all_hens.clear()
        self._frame_count = 0
