"""
Zone-based hen counting with trajectory tracking.

BoT-SORT provides frame-to-frame tracking with OSNet appearance ReID embeddings
for robust identity maintenance across occlusions. This module adds:
1. Zone-based counting (count at entry/exit boundaries)
2. Lost track recovery via spatial + temporal proximity (fallback for long occlusions)
3. Global ID assignment mapping temporary tracker IDs to persistent hen IDs
"""

import time
import numpy as np
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TrackState:
    track_id: int
    centroid: tuple[float, float]
    bbox: dict
    first_seen: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    last_zone: str = ""
    total_zone_entries: int = 0
    trajectory: list[tuple[float, float]] = field(default_factory=list)


class ZoneDefinition:
    def __init__(self, name: str, polygon: list[tuple[float, float]]):
        self.name = name
        self.polygon = polygon

    def contains(self, point: tuple[float, float]) -> bool:
        x, y = point
        n = len(self.polygon)
        inside = False
        j = n - 1
        for i in range(n):
            xi, yi = self.polygon[i]
            xj, yj = self.polygon[j]
            if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
                inside = not inside
            j = i
        return inside


class ZoneBasedCounter:
    def __init__(self, frame_width: int, frame_height: int):
        self.frame_width = frame_width
        self.frame_height = frame_height
        self._tracks: dict[int, TrackState] = {}
        self._global_id_counter = 0
        self._track_to_global: dict[int, int] = {}
        self._global_registry: dict[int, dict] = {}
        self._previous_track_ids: set[int] = set()
        self._zones: list[ZoneDefinition] = []
        self._zone_counts: dict[str, int] = {}
        self._max_lost_seconds = 30.0
        self._max_centroid_distance = 150.0

    def add_zone(self, zone: ZoneDefinition):
        self._zones.append(zone)
        self._zone_counts[zone.name] = 0

    def add_default_zones(self):
        cx = self.frame_width / 2
        margin = 60
        self.add_zone(ZoneDefinition("entry_left", [
            (0, 0), (margin, 0), (margin, self.frame_height), (0, self.frame_height)
        ]))
        self.add_zone(ZoneDefinition("entry_right", [
            (self.frame_width - margin, 0), (self.frame_width, 0),
            (self.frame_width, self.frame_height), (self.frame_width - margin, self.frame_height)
        ]))
        self.add_zone(ZoneDefinition("center", [
            (cx - 50, self.frame_height * 0.2), (cx + 50, self.frame_height * 0.2),
            (cx + 50, self.frame_height * 0.8), (cx - 50, self.frame_height * 0.8)
        ]))

    def _get_zone(self, centroid: tuple[float, float]) -> str:
        for zone in self._zones:
            if zone.contains(centroid):
                return zone.name
        return "open_area"

    def _assign_global_id(self, track_id: int, centroid: tuple[float, float]) -> int:
        if track_id in self._track_to_global:
            return self._track_to_global[track_id]

        now = time.time()
        best_match = None
        best_score = 0.0

        for gid, info in self._global_registry.items():
            if now - info["last_seen"] > self._max_lost_seconds:
                continue
            dist = np.sqrt(
                (centroid[0] - info["centroid"][0]) ** 2 +
                (centroid[1] - info["centroid"][1]) ** 2
            )
            if dist > self._max_centroid_distance:
                continue
            recency = 1.0 - (now - info["last_seen"]) / self._max_lost_seconds
            spatial = 1.0 - dist / self._max_centroid_distance
            score = 0.6 * spatial + 0.4 * recency
            if score > best_score and score > 0.3:
                best_score = score
                best_match = gid

        if best_match is not None:
            self._track_to_global[track_id] = best_match
            self._global_registry[best_match]["centroid"] = centroid
            self._global_registry[best_match]["last_seen"] = now
            return best_match

        self._global_id_counter += 1
        gid = self._global_id_counter
        self._track_to_global[track_id] = gid
        self._global_registry[gid] = {
            "centroid": centroid,
            "last_seen": now,
        }
        return gid

    def process_frame(
        self,
        detections: list[dict],
        track_ids: list[Optional[int]],
    ) -> dict:
        now = time.time()
        current_track_ids = set()
        matched_dets = []

        for det, track_id in zip(detections, track_ids):
            if track_id is None:
                continue

            current_track_ids.add(track_id)
            centroid = (
                det["bbox"]["x"] + det["bbox"]["w"] / 2,
                det["bbox"]["y"] + det["bbox"]["h"] / 2,
            )
            zone = self._get_zone(centroid)
            global_id = self._assign_global_id(track_id, centroid)

            if track_id not in self._tracks:
                self._tracks[track_id] = TrackState(
                    track_id=track_id,
                    centroid=centroid,
                    bbox=det["bbox"],
                )

            tstate = self._tracks[track_id]
            tstate.centroid = centroid
            tstate.bbox = det["bbox"]
            tstate.last_seen = now
            tstate.trajectory.append(centroid)
            if len(tstate.trajectory) > 60:
                tstate.trajectory.pop(0)

            if tstate.last_zone and tstate.last_zone != zone:
                if zone in ("entry_left", "entry_right"):
                    tstate.total_zone_entries += 1
                    self._zone_counts[zone] = self._zone_counts.get(zone, 0) + 1

            tstate.last_zone = zone

            matched_dets.append({
                **det,
                "track_id": track_id,
                "global_id": global_id,
                "zone": zone,
            })

        lost_tracks = self._previous_track_ids - current_track_ids
        for tid in lost_tracks:
            if tid in self._tracks:
                age = now - self._tracks[tid].last_seen
                if age > self._max_lost_seconds:
                    del self._tracks[tid]

        self._previous_track_ids = current_track_ids

        unique_ids = set(self._track_to_global.values())

        return {
            "detections": matched_dets,
            "current_count": len(current_track_ids),
            "unique_count": len(unique_ids),
            "total_seen": self._global_id_counter,
            "zone_counts": dict(self._zone_counts),
        }

    def get_unique_count(self) -> int:
        return len(set(self._track_to_global.values()))

    def get_current_visible(self) -> int:
        return len([t for t in self._tracks.values()
                    if time.time() - t.last_seen < 2.0])

    def get_total_seen(self) -> int:
        return self._global_id_counter

    def get_zone_counts(self) -> dict[str, int]:
        return dict(self._zone_counts)

    def get_trajectories(self) -> dict[int, list[tuple[float, float]]]:
        return {tid: list(t.trajectory) for tid, t in self._tracks.items()}

    def reset(self):
        self._tracks.clear()
        self._global_id_counter = 0
        self._track_to_global.clear()
        self._global_registry.clear()
        self._previous_track_ids.clear()
        for zone_name in self._zone_counts:
            self._zone_counts[zone_name] = 0
