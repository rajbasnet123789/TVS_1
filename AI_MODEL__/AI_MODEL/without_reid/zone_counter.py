"""
Zone-Based Hen Counter — Line Crossing Detection with Trajectory Smoothing.

Counting logic:
  - Each camera has one or more counting lines (horizontal or arbitrary).
  - When a tracked hen crosses a line INWARD  → count +1
  - When a tracked hen crosses a line OUTWARD → count -1
  - Trajectory is smoothed with exponential moving average before crossing test.
  - Lost tracks cleaned up after configurable timeout.
"""
import time
import logging
import numpy as np
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class HenTrack:
    track_id: int
    centroid: tuple[float, float]
    bbox: tuple[int, int, int, int]
    first_seen: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    trajectory: list[tuple[float, float]] = field(default_factory=list)
    smoothed: tuple[float, float] = (0.0, 0.0)
    crossed_line: bool = False
    counted: bool = False
    direction: str = ""
    smoothing_alpha: float = 0.4

    def update_smoothed(self, raw: tuple[float, float]) -> tuple[float, float]:
        sx, sy = self.smoothed
        rx, ry = raw
        if sx == 0.0 and sy == 0.0:
            self.smoothed = raw
        else:
            a = self.smoothing_alpha
            self.smoothed = (a * rx + (1 - a) * sx, a * ry + (1 - a) * sy)
        return self.smoothed


class CountingLine:
    def __init__(self, name: str, p1: tuple[float, float], p2: tuple[float, float],
                 direction: str = "inward", active: bool = True):
        self.name = name
        self.p1 = np.array(p1, dtype=np.float32)
        self.p2 = np.array(p2, dtype=np.float32)
        self.direction = direction
        self.active = active

    def intersects(self, a: tuple[float, float], b: tuple[float, float]) -> bool:
        x1, y1 = a
        x2, y2 = b
        x3, y3 = self.p1
        x4, y4 = self.p2
        denom = (x4 - x3) * (y1 - y2) - (x1 - x2) * (y4 - y3)
        if abs(denom) < 1e-10:
            return False
        t = ((x3 - x1) * (y1 - y2) - (x1 - x2) * (y3 - y1)) / denom
        u = -((x4 - x3) * (y3 - y1) - (x3 - x1) * (y4 - y3)) / denom
        return 0 <= t <= 1 and 0 <= u <= 1

    def side_of(self, point: tuple[float, float]) -> str:
        vx = self.p2[0] - self.p1[0]
        vy = self.p2[1] - self.p1[1]
        cross = vx * (point[1] - self.p1[1]) - vy * (point[0] - self.p1[0])
        return "above" if cross < 0 else "below"

    def crossing_direction(self, prev: tuple[float, float], curr: tuple[float, float]) -> Optional[str]:
        prev_side = self.side_of(prev)
        curr_side = self.side_of(curr)
        if prev_side == curr_side:
            return None
        if self.direction == "inward":
            return "in" if curr_side == "below" else "out"
        return "out" if curr_side == "below" else "in"


class ZoneBasedCounter:
    def __init__(self, frame_width: int, frame_height: int, camera_id: str = ""):
        self.frame_width = frame_width
        self.frame_height = frame_height
        self.camera_id = camera_id
        self._tracks: dict[int, HenTrack] = {}
        self._counting_lines: list[CountingLine] = []
        self._net_count = 0
        self._in_count = 0
        self._out_count = 0
        self._total_passed_in = 0
        self._total_passed_out = 0
        self._max_lost_seconds = 30.0
        self._max_trajectory = 60
        self._last_cleanup = time.time()
        self._cleanup_interval = 5.0

    def add_counting_line(self, line: CountingLine):
        self._counting_lines.append(line)

    def add_default_lines(self):
        margin_y = int(self.frame_height * 0.3)
        self.add_counting_line(CountingLine(
            "top_entry",
            (0, margin_y), (self.frame_width, margin_y),
            direction="inward"
        ))
        margin_y2 = int(self.frame_height * 0.7)
        self.add_counting_line(CountingLine(
            "bottom_exit",
            (0, margin_y2), (self.frame_width, margin_y2),
            direction="outward"
        ))

    def process_frame(self, detections: list[dict],
                      track_ids: list[Optional[int]]) -> dict:
        current_ids: set[int] = set()
        now = time.time()

        for det, tid in zip(detections, track_ids):
            if tid is None:
                continue
            current_ids.add(tid)

            cx = det["bbox"][0] + det["bbox"][2] / 2.0
            cy = det["bbox"][1] + det["bbox"][3] / 2.0
            centroid = (cx, cy)

            if tid not in self._tracks:
                self._tracks[tid] = HenTrack(
                    track_id=tid,
                    centroid=centroid,
                    bbox=tuple(det["bbox"]),
                )
                self._tracks[tid].smoothed = centroid

            track = self._tracks[tid]
            prev_smoothed = track.smoothed
            smoothed = track.update_smoothed(centroid)
            track.centroid = centroid
            track.bbox = tuple(det["bbox"])
            track.last_seen = now
            track.trajectory.append(smoothed)
            if len(track.trajectory) > self._max_trajectory:
                track.trajectory.pop(0)

            for line in self._counting_lines:
                if not line.active:
                    continue
                if line.intersects(prev_smoothed, smoothed):
                    if not track.counted:
                        cd = line.crossing_direction(prev_smoothed, smoothed)
                        if cd == "in":
                            self._net_count += 1
                            self._in_count += 1
                            self._total_passed_in += 1
                            track.counted = True
                            track.direction = "in"
                            logger.debug(f"Track {tid} crossed {line.name} IN")
                        elif cd == "out":
                            self._net_count -= 1
                            self._out_count += 1
                            self._total_passed_out += 1
                            track.counted = True
                            track.direction = "out"
                            logger.debug(f"Track {tid} crossed {line.name} OUT")

        if now - self._last_cleanup > self._cleanup_interval:
            expired = [tid for tid, t in self._tracks.items()
                       if now - t.last_seen > self._max_lost_seconds]
            for tid in expired:
                del self._tracks[tid]
            if expired:
                logger.info(f"Cleaned {len(expired)} expired tracks for {self.camera_id}")
            self._last_cleanup = now

        return {
            "net_count": self._net_count,
            "in_count": self._in_count,
            "out_count": self._out_count,
            "total_passed_in": self._total_passed_in,
            "total_passed_out": self._total_passed_out,
            "active_tracks": len(current_ids),
            "total_tracked": len(self._tracks),
        }

    def get_net_count(self) -> int:
        return self._net_count

    def reset(self):
        self._tracks.clear()
        self._net_count = 0
        self._in_count = 0
        self._out_count = 0
        self._total_passed_in = 0
        self._total_passed_out = 0
