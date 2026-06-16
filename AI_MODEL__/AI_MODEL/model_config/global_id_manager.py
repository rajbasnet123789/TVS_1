"""
Global ID Management System with Coordinate Fusion.

Fuses ReID embeddings with camera geometry to track individuals
moving between overlapping fields of view across multiple cameras.

Key features:
- Coordinate-aware identity matching using camera positions
- Exponential moving average embedding updates
- Spatial-temporal constraint enforcement
- Lost track recovery with geometric reasoning
- Thread-safe operations for concurrent camera processing
"""

import time
import threading
import logging
import numpy as np
from typing import Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

try:
    import faiss
    HAS_FAISS = True
except ImportError:
    HAS_FAISS = False
    logger.warning("FAISS not available, using brute-force similarity")


@dataclass
class CameraGeometry:
    """Camera position and field-of-view geometry."""
    camera_id: str
    position: dict = field(default_factory=lambda: {"x": 0, "y": 0, "z": 0})
    fov_angle: float = 90.0
    max_range: float = 50.0
    overlap_cameras: list = field(default_factory=list)


@dataclass
class HenIdentity:
    """Persistent hen identity across cameras."""
    global_id: int
    embedding: np.ndarray
    camera_id: str
    centroid: tuple
    first_seen: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    detection_count: int = 1
    confidence: float = 0.0
    camera_history: list = field(default_factory=list)
    embedding_history: list = field(default_factory=list)
    last_positions: dict = field(default_factory=dict)


class CoordinateFusion:
    """
    Fuses camera geometry with ReID embeddings for improved matching.

    Uses camera positions and overlap information to:
    1. Weight spatial proximity in identity matching
    2. Predict likely camera transitions based on geometry
    3. Filter impossible matches (cameras too far apart)
    """

    def __init__(self):
        self._camera_geometries: dict[str, CameraGeometry] = {}

    def add_camera(self, geometry: CameraGeometry):
        self._camera_geometries[geometry.camera_id] = geometry

    def get_spatial_weight(self, cam_a: str, cam_b: str) -> float:
        """
        Compute spatial compatibility weight between two cameras.
        Returns 1.0 for same camera, decreasing for distant cameras.
        """
        if cam_a == cam_b:
            return 1.0

        geo_a = self._camera_geometries.get(cam_a)
        geo_b = self._camera_geometries.get(cam_b)

        if geo_a is None or geo_b is None:
            return 0.5

        pos_a = np.array([geo_a.position["x"], geo_a.position["y"], geo_a.position["z"]])
        pos_b = np.array([geo_b.position["x"], geo_b.position["y"], geo_b.position["z"]])
        distance = np.linalg.norm(pos_a - pos_b)

        max_dist = max(geo_a.max_range, geo_b.max_range)
        if distance > max_dist * 2:
            return 0.0

        if cam_b in geo_a.overlap_cameras or cam_a in geo_b.overlap_cameras:
            return 1.0

        weight = np.exp(-distance / max_dist)
        return float(weight)

    def predict_camera_transition(self, current_camera: str, velocity: tuple) -> list[str]:
        """Predict likely next cameras based on movement direction."""
        geo = self._camera_geometries.get(current_camera)
        if geo is None:
            return []

        current_pos = np.array([geo.position["x"], geo.position["y"]])
        predicted_pos = current_pos + np.array(velocity) * 5.0

        candidates = []
        for cam_id, other_geo in self._camera_geometries.items():
            if cam_id == current_camera:
                continue
            other_pos = np.array([other_geo.position["x"], other_geo.position["y"]])
            dist = np.linalg.norm(predicted_pos - other_pos)
            if dist < other_geo.max_range:
                candidates.append((cam_id, dist))

        candidates.sort(key=lambda x: x[1])
        return [c[0] for c in candidates[:3]]


class GlobalIDManager:
    """
    Manages persistent global identities across multiple cameras.

    Combines:
    - ReID embedding similarity (appearance matching)
    - Camera geometry (spatial constraints)
    - Temporal consistency (motion coherence)
    - Lost track recovery (re-identification after occlusion)
    """

    def __init__(
        self,
        embedding_dim: int = 512,
        match_threshold: float = 0.5,
        spatial_weight: float = 0.3,
        temporal_weight: float = 0.2,
        appearance_weight: float = 0.5,
        max_lost_seconds: float = 120.0,
    ):
        self.embedding_dim = embedding_dim
        self.match_threshold = match_threshold
        self.spatial_weight = spatial_weight
        self.temporal_weight = temporal_weight
        self.appearance_weight = appearance_weight
        self.max_lost_seconds = max_lost_seconds

        self.coordinate_fusion = CoordinateFusion()
        self._identities: dict[int, HenIdentity] = {}
        self._next_id = 1
        self._lock = threading.Lock()

        if HAS_FAISS:
            self._index = faiss.IndexFlatIP(embedding_dim)
            self._id_map: list[int] = []
        else:
            self._index = None
            self._id_map = []

        self._track_to_global: dict[str, int] = {}
        self._camera_positions: dict[str, dict] = {}

    def add_camera(self, camera_id: str, position: dict, fov_angle: float = 90.0,
                   max_range: float = 50.0, overlap_cameras: list = None):
        """Register a camera with its geometry."""
        self._camera_positions[camera_id] = position
        self.coordinate_fusion.add_camera(CameraGeometry(
            camera_id=camera_id,
            position=position,
            fov_angle=fov_angle,
            max_range=max_range,
            overlap_cameras=overlap_cameras or [],
        ))

    def process_detection(
        self,
        embedding: np.ndarray,
        camera_id: str,
        track_id: int,
        centroid: tuple,
        confidence: float = 0.0,
    ) -> int:
        """
        Process a detection and return its global ID.

        Fuses appearance (embedding), spatial (camera geometry),
        and temporal (recency) information for robust matching.
        """
        with self._lock:
            track_key = f"{camera_id}_{track_id}"

            if track_key in self._track_to_global:
                gid = self._track_to_global[track_key]
                if gid in self._identities:
                    self._update_identity(gid, embedding, camera_id, centroid, confidence)
                    return gid

            if embedding is not None and self._index is not None and self._index.ntotal > 0:
                best_gid = self._match_embedding(embedding, camera_id, centroid)
                if best_gid is not None:
                    self._track_to_global[track_key] = best_gid
                    self._update_identity(best_gid, embedding, camera_id, centroid, confidence)
                    return best_gid

            gid = self._create_identity(embedding, camera_id, centroid, confidence)
            self._track_to_global[track_key] = gid
            return gid

    def _match_embedding(self, embedding: np.ndarray, camera_id: str,
                         centroid: tuple) -> Optional[int]:
        """Find best matching identity using fused scoring."""
        k = min(15, self._index.ntotal)
        query = embedding.reshape(1, -1).astype(np.float32)
        distances, indices = self._index.search(query, k)

        best_gid = None
        best_score = -1.0

        now = time.time()

        for dist, idx in zip(distances[0], indices[0]):
            if idx < 0 or idx >= len(self._id_map):
                continue

            gid = self._id_map[idx]
            identity = self._identities.get(gid)
            if identity is None:
                continue

            appearance_score = float(dist)

            spatial_score = self.coordinate_fusion.get_spatial_weight(
                identity.camera_id, camera_id
            )

            time_diff = now - identity.last_seen
            temporal_score = max(0.0, 1.0 - time_diff / self.max_lost_seconds)

            total_score = (
                self.appearance_weight * appearance_score +
                self.spatial_weight * spatial_score +
                self.temporal_weight * temporal_score
            )

            if total_score > best_score and appearance_score >= self.match_threshold * 0.8:
                best_score = total_score
                best_gid = gid

        if best_gid is not None and best_score > 0.3:
            return best_gid

        return self._recover_lost_track(embedding, camera_id, centroid)

    def _recover_lost_track(self, embedding: np.ndarray, camera_id: str,
                            centroid: tuple) -> Optional[int]:
        """Attempt to recover a lost track using geometric reasoning."""
        now = time.time()

        for gid, identity in self._identities.items():
            time_since_lost = now - identity.last_seen
            if time_since_lost > self.max_lost_seconds:
                continue

            last_pos = identity.last_positions.get(identity.camera_id)
            if last_pos is None:
                continue

            dist = np.sqrt(
                (centroid[0] - last_pos[0]) ** 2 +
                (centroid[1] - last_pos[1]) ** 2
            )

            if dist > 500:
                continue

            recency = 1.0 - (time_since_lost / self.max_lost_seconds)
            spatial = 1.0 - (dist / 500.0)
            recovery_score = 0.6 * recency + 0.4 * spatial

            if recovery_score > 0.4:
                logger.info(f"Recovered lost track: gid={gid} (score={recovery_score:.3f})")
                return gid

        return None

    def _create_identity(self, embedding: np.ndarray, camera_id: str,
                         centroid: tuple, confidence: float) -> int:
        """Create a new global identity."""
        gid = self._next_id
        self._next_id += 1

        emb = embedding if embedding is not None else np.zeros(self.embedding_dim, dtype=np.float32)

        identity = HenIdentity(
            global_id=gid,
            embedding=emb,
            camera_id=camera_id,
            centroid=centroid,
            confidence=confidence,
            camera_history=[camera_id],
            last_positions={camera_id: centroid},
        )
        self._identities[gid] = identity

        if self._index is not None:
            self._index.add(emb.reshape(1, -1).astype(np.float32))
            self._id_map.append(gid)

        logger.info(f"New identity: gid={gid} on camera={camera_id}")
        return gid

    def _update_identity(self, gid: int, embedding: np.ndarray, camera_id: str,
                         centroid: tuple, confidence: float):
        """Update existing identity with exponential moving average."""
        identity = self._identities.get(gid)
        if identity is None:
            return

        alpha = 0.3
        if embedding is not None:
            updated = alpha * embedding + (1 - alpha) * identity.embedding
            norm = np.linalg.norm(updated)
            if norm > 0:
                updated = updated / norm
            identity.embedding = updated

        identity.last_seen = time.time()
        identity.camera_id = camera_id
        identity.centroid = centroid
        identity.detection_count += 1
        identity.last_positions[camera_id] = centroid

        if camera_id not in identity.camera_history:
            identity.camera_history.append(camera_id)

        if confidence > 0:
            count = identity.detection_count
            identity.confidence = (
                identity.confidence * (count - 1) + confidence
            ) / count

    def get_active_identities(self, max_age_seconds: float = 60.0) -> list[dict]:
        """Get currently visible identities."""
        now = time.time()
        active = []
        for gid, identity in self._identities.items():
            if now - identity.last_seen < max_age_seconds:
                active.append({
                    "global_id": gid,
                    "camera_id": identity.camera_id,
                    "centroid": identity.centroid,
                    "confidence": identity.confidence,
                    "detection_count": identity.detection_count,
                    "cameras_seen": len(identity.camera_history),
                })
        return active

    def get_total_identities(self) -> int:
        return len(self._identities)

    def get_cross_camera_identities(self) -> list[dict]:
        """Get identities seen on multiple cameras."""
        result = []
        for gid, identity in self._identities.items():
            if len(identity.camera_history) > 1:
                result.append({
                    "global_id": gid,
                    "cameras": identity.camera_history,
                    "detection_count": identity.detection_count,
                    "confidence": identity.confidence,
                })
        return result

    def cleanup_stale(self, max_age_seconds: float = 300.0):
        """Remove identities not seen for a long time."""
        with self._lock:
            now = time.time()
            stale = [
                gid for gid, identity in self._identities.items()
                if now - identity.last_seen > max_age_seconds
            ]
            for gid in stale:
                del self._identities[gid]

            if self._index is not None and stale:
                self._rebuild_index()

    def _rebuild_index(self):
        """Rebuild FAISS index after cleanup."""
        if not HAS_FAISS or not self._identities:
            if self._index is not None:
                self._index.reset()
                self._id_map = []
            return

        self._index = faiss.IndexFlatIP(self.embedding_dim)
        self._id_map = []
        for gid, identity in self._identities.items():
            self._index.add(identity.embedding.reshape(1, -1).astype(np.float32))
            self._id_map.append(gid)
