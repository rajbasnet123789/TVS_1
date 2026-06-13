import logging
import time
import threading
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

try:
    import faiss
    HAS_FAISS = True
except ImportError:
    HAS_FAISS = False
    logger.warning("faiss not available, using brute-force cosine similarity")


class EmbeddingGallery:
    def __init__(self, embedding_dim: int = 512, max_identities: int = 10000):
        self.embedding_dim = embedding_dim
        self.max_identities = max_identities
        self._lock = threading.Lock()

        self._embeddings: dict[int, np.ndarray] = {}
        self._metadata: dict[int, dict] = {}
        self._next_id = 1

        if HAS_FAISS:
            self._index = faiss.IndexFlatIP(embedding_dim)
            self._id_map: list[int] = []
            logger.info("FAISS gallery initialized (Inner Product / cosine similarity)")
        else:
            self._index = None
            self._id_map = []
            logger.info("Fallback brute-force gallery initialized")

    def add(
        self,
        embedding: np.ndarray,
        camera_id: str,
        confidence: float = 0.0,
        metadata: Optional[dict] = None,
    ) -> int:
        with self._lock:
            global_id = self._next_id
            self._next_id += 1

            self._embeddings[global_id] = embedding.copy()
            self._metadata[global_id] = {
                "camera_id": camera_id,
                "confidence": confidence,
                "first_seen": time.time(),
                "last_seen": time.time(),
                "detection_count": 1,
                **(metadata or {}),
            }

            if self._index is not None:
                self._index.add(embedding.reshape(1, -1).astype(np.float32))
                self._id_map.append(global_id)
            else:
                self._id_map.append(global_id)

            return global_id

    def search(
        self,
        query_embedding: np.ndarray,
        k: int = 5,
        threshold: float = 0.5,
    ) -> list[tuple[int, float]]:
        with self._lock:
            if not self._id_map:
                return []

            if self._index is not None and self._index.ntotal > 0:
                k = min(k, self._index.ntotal)
                query = query_embedding.reshape(1, -1).astype(np.float32)
                distances, indices = self._index.search(query, k)

                results = []
                for dist, idx in zip(distances[0], indices[0]):
                    if idx < 0 or idx >= len(self._id_map):
                        continue
                    gid = self._id_map[idx]
                    if dist >= threshold:
                        results.append((gid, float(dist)))
                return results
            else:
                return self._brute_force_search(query_embedding, k, threshold)

    def _brute_force_search(
        self,
        query: np.ndarray,
        k: int,
        threshold: float,
    ) -> list[tuple[int, float]]:
        if not self._embeddings:
            return []

        ids = list(self._embeddings.keys())
        matrix = np.stack([self._embeddings[gid] for gid in ids]).astype(np.float32)
        query_norm = query.astype(np.float32).reshape(1, -1)

        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1, norms)
        matrix_normalized = matrix / norms

        q_norm = np.linalg.norm(query_norm)
        if q_norm == 0:
            return []
        query_normalized = query_norm / q_norm

        scores = matrix_normalized @ query_normalized.T
        scores = scores.flatten()

        top_k = np.argsort(scores)[::-1][:k]
        results = []
        for idx in top_k:
            if scores[idx] >= threshold:
                results.append((ids[idx], float(scores[idx])))
        return results

    def update(
        self,
        global_id: int,
        embedding: np.ndarray,
        camera_id: str,
        confidence: float = 0.0,
    ):
        with self._lock:
            if global_id not in self._embeddings:
                return

            old_emb = self._embeddings[global_id]
            alpha = 0.3
            updated = alpha * embedding + (1 - alpha) * old_emb
            norm = np.linalg.norm(updated)
            if norm > 0:
                updated = updated / norm

            self._embeddings[global_id] = updated
            self._metadata[global_id]["last_seen"] = time.time()
            self._metadata[global_id]["camera_id"] = camera_id
            self._metadata[global_id]["detection_count"] = (
                self._metadata[global_id].get("detection_count", 0) + 1
            )
            if confidence > 0:
                old_conf = self._metadata[global_id].get("confidence", 0)
                count = self._metadata[global_id]["detection_count"]
                self._metadata[global_id]["confidence"] = (
                    old_conf * (count - 1) + confidence
                ) / count

    def get_metadata(self, global_id: int) -> Optional[dict]:
        return self._metadata.get(global_id)

    def get_all_ids(self) -> list[int]:
        return list(self._embeddings.keys())

    def get_active_ids(self, max_age_seconds: float = 60.0) -> list[int]:
        now = time.time()
        return [
            gid for gid, meta in self._metadata.items()
            if now - meta["last_seen"] < max_age_seconds
        ]

    def remove_stale(self, max_age_seconds: float = 300.0):
        with self._lock:
            now = time.time()
            stale_ids = [
                gid for gid, meta in self._metadata.items()
                if now - meta["last_seen"] > max_age_seconds
            ]
            for gid in stale_ids:
                del self._embeddings[gid]
                del self._metadata[gid]
                if gid in self._id_map:
                    self._id_map.remove(gid)

            if self._index is not None and stale_ids:
                self._rebuild_index()

    def _rebuild_index(self):
        if not HAS_FAISS or not self._embeddings:
            if self._index is not None:
                self._index.reset()
                self._id_map = []
            return

        self._index = faiss.IndexFlatIP(self.embedding_dim)
        self._id_map = []
        if self._embeddings:
            matrix = np.stack(list(self._embeddings.values())).astype(np.float32)
            self._index.add(matrix)
            self._id_map = list(self._embeddings.keys())

    def size(self) -> int:
        return len(self._embeddings)
