import logging
import time
from typing import Optional

import numpy as np

from app.detection.mcmt.embeddings import EmbeddingExtractor, HenIdentity
from app.detection.mcmt.gallery import EmbeddingGallery

logger = logging.getLogger(__name__)


def _spatial_distance(loc_a: dict, loc_b: dict) -> float:
    return np.sqrt(
        (loc_a["x"] - loc_b["x"]) ** 2
        + (loc_a["y"] - loc_b["y"]) ** 2
        + (loc_a["z"] - loc_b["z"]) ** 2
    )


class GlobalTracker:
    def __init__(
        self,
        match_threshold: float = 0.5,
        spatial_constraint_distance: float = 50.0,
        temporal_constraint_seconds: float = 5.0,
        embedding_dim: int = 2152,
    ):
        self.match_threshold = match_threshold
        self.spatial_constraint_distance = spatial_constraint_distance
        self.temporal_constraint_seconds = temporal_constraint_seconds

        self.extractor = EmbeddingExtractor()
        self.gallery = EmbeddingGallery(embedding_dim=embedding_dim)

        self._camera_locations: dict[str, dict] = {}
        self._global_identities: dict[int, HenIdentity] = {}
        self._next_global_id = 1

    async def load(self):
        await self.extractor.load()
        await self._load_camera_locations()
        logger.info("GlobalTracker loaded")

    async def _load_camera_locations(self):
        try:
            from app.database import async_session
            from sqlalchemy import select
            from app.cameras.models import Camera

            async with async_session() as session:
                result = await session.execute(select(Camera))
                cameras = result.scalars().all()
                for cam in cameras:
                    self._camera_locations[str(cam.id)] = {
                        "x": cam.pos_x or 0,
                        "y": cam.pos_y or 0,
                        "z": cam.pos_z or 0,
                    }
                logger.info(f"Loaded positions for {len(self._camera_locations)} cameras")
        except Exception as e:
            logger.warning(f"Could not load camera positions from DB: {e}")

    def set_camera_location(self, camera_id: str, x: int, y: int, z: int = 0):
        self._camera_locations[camera_id] = {"x": x, "y": y, "z": z}

    def get_camera_location(self, camera_id: str) -> dict:
        return self._camera_locations.get(camera_id, {"x": 0, "y": 0, "z": 0})

    def process_frame(
        self,
        detections: list[dict],
        track_ids: list[Optional[int]],
        frame: np.ndarray,
        camera_id: str,
    ) -> list[dict]:
        if not detections:
            return []

        bboxes = [d["bbox"] for d in detections]
        embeddings = self.extractor.extract(frame, bboxes)

        results = []
        for det, track_id, embedding in zip(detections, track_ids, embeddings):
            entry = {**det}

            if embedding is None or track_id is None:
                entry["global_id"] = None
                results.append(entry)
                continue

            global_id = self._match_or_create(
                embedding=embedding,
                camera_id=camera_id,
                confidence=det.get("confidence", 0.0),
            )

            entry["global_id"] = global_id
            results.append(entry)

        return results

    def _match_or_create(
        self,
        embedding: np.ndarray,
        camera_id: str,
        confidence: float = 0.0,
    ) -> int:
        matches = self.gallery.search(
            query_embedding=embedding,
            k=5,
            threshold=self.match_threshold,
        )

        best_match_id = None
        best_score = 0.0

        for gid, score in matches:
            meta = self.gallery.get_metadata(gid)
            if meta is None:
                continue

            last_camera = meta.get("camera_id", "")
            last_seen = meta.get("last_seen", 0)
            time_diff = time.time() - last_seen

            if last_camera != camera_id:
                loc_a = self._camera_locations.get(last_camera, {"x": 0, "y": 0, "z": 0})
                loc_b = self._camera_locations.get(camera_id, {"x": 0, "y": 0, "z": 0})
                spatial_dist = _spatial_distance(loc_a, loc_b)

                if spatial_dist > self.spatial_constraint_distance:
                    if time_diff < self.temporal_constraint_seconds:
                        logger.debug(
                            f"Rejected match gid={gid}: spatial constraint "
                            f"({spatial_dist:.1f} > {self.spatial_constraint_distance})"
                        )
                        continue

            if score > best_score:
                best_score = score
                best_match_id = gid

        if best_match_id is not None:
            self.gallery.update(
                global_id=best_match_id,
                embedding=embedding,
                camera_id=camera_id,
                confidence=confidence,
            )
            return best_match_id

        global_id = self.gallery.add(
            embedding=embedding,
            camera_id=camera_id,
            confidence=confidence,
        )
        self._next_global_id = max(self._next_global_id, global_id + 1)
        logger.info(f"New identity created: global_id={global_id} on camera={camera_id}")
        return global_id

    def get_active_identities(self, max_age_seconds: float = 60.0) -> list[dict]:
        active_ids = self.gallery.get_active_ids(max_age_seconds)
        result = []
        for gid in active_ids:
            meta = self.gallery.get_metadata(gid)
            if meta:
                result.append({
                    "global_id": gid,
                    "camera_id": meta["camera_id"],
                    "last_seen": meta["last_seen"],
                    "detection_count": meta.get("detection_count", 1),
                    "confidence": meta.get("confidence", 0.0),
                })
        return result

    def get_total_identities(self) -> int:
        return self.gallery.size()

    def cleanup_stale(self, max_age_seconds: float = 300.0):
        self.gallery.remove_stale(max_age_seconds)
