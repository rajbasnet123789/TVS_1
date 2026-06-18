"""
FAISS-based Face Embedding Gallery with JSON Persistence.

Manages a searchable gallery of known person face embeddings using
FAISS IndexFlatIP for fast cosine similarity search (on L2-normalized
vectors, inner product = cosine similarity).

Features:
- JSON serialization for persistent storage
- EMA (Exponential Moving Average) embedding updates for identity refinement
- Brute-force numpy fallback when FAISS unavailable
- Thread-safe operations for concurrent access
"""

import os
import json
import time
import threading
import numpy as np
from typing import Optional
from dataclasses import dataclass, field

try:
    import faiss
    HAS_FAISS = True
except ImportError:
    HAS_FAISS = False


@dataclass
class PersonRecord:
    """Stored record for a known person."""
    name: str
    embedding: np.ndarray
    num_images: int = 1
    created_at: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    match_count: int = 0


class FaceGallery:
    """
    FAISS-powered gallery for face embedding search and storage.

    Uses IndexFlatIP (Inner Product) on L2-normalized vectors,
    which is equivalent to cosine similarity search.
    """

    def __init__(self, embedding_dim: int = 512, match_threshold: float = 0.45):
        self._dim = embedding_dim
        self._threshold = match_threshold
        self._records: dict[str, PersonRecord] = {}
        self._lock = threading.Lock()

        if HAS_FAISS:
            self._index = faiss.IndexFlatIP(embedding_dim)
            self._id_map: list[str] = []
        else:
            self._index = None
            self._id_map = []
            print("[FaceGallery] FAISS not available, using brute-force similarity")

    @property
    def size(self) -> int:
        return len(self._records)

    def add(self, name: str, embedding: np.ndarray, num_images: int = 1):
        """
        Add or update a person in the gallery.

        If the name already exists, applies EMA update to refine embedding.
        """
        with self._lock:
            if name in self._records:
                self._update_embedding(name, embedding, num_images)
            else:
                self._create_record(name, embedding, num_images)

    def _create_record(self, name: str, embedding: np.ndarray, num_images: int):
        """Create a new person record."""
        record = PersonRecord(
            name=name,
            embedding=embedding.copy(),
            num_images=num_images,
        )
        self._records[name] = record

        if self._index is not None:
            self._index.add(embedding.reshape(1, -1).astype(np.float32))
            self._id_map.append(name)

        print(f"[FaceGallery] Added '{name}' (images={num_images})")

    def _update_embedding(self, name: str, embedding: np.ndarray, num_images: int):
        """Update existing person with EMA embedding refinement."""
        record = self._records[name]
        alpha = 0.3
        updated = alpha * embedding + (1 - alpha) * record.embedding
        norm = np.linalg.norm(updated)
        if norm > 0:
            updated = updated / norm
        record.embedding = updated
        record.num_images += num_images
        record.last_seen = time.time()
        record.match_count += 1

        # Rebuild FAISS index with updated embedding
        self._rebuild_index()

        print(f"[FaceGallery] Updated '{name}' "
              f"(total_images={record.num_images}, matches={record.match_count})")

    def search(self, embedding: np.ndarray) -> Optional[tuple[str, float]]:
        """
        Search gallery for the best matching person.

        Args:
            embedding: L2-normalized 512-dim query embedding.

        Returns:
            (name, similarity_score) if match above threshold, else None.
        """
        if not self._records:
            return None

        with self._lock:
            if self._index is not None and self._index.ntotal > 0:
                return self._faiss_search(embedding)
            else:
                return self._brute_force_search(embedding)

    def _faiss_search(self, embedding: np.ndarray) -> Optional[tuple[str, float]]:
        """Search using FAISS index."""
        query = embedding.reshape(1, -1).astype(np.float32)
        k = min(5, self._index.ntotal)
        distances, indices = self._index.search(query, k)

        for dist, idx in zip(distances[0], indices[0]):
            if idx < 0 or idx >= len(self._id_map):
                continue

            name = self._id_map[idx]
            similarity = float(dist)

            if similarity >= self._threshold:
                return (name, similarity)

        return None

    def _brute_force_search(self, embedding: np.ndarray) -> Optional[tuple[str, float]]:
        """Fallback brute-force cosine similarity search."""
        best_name = None
        best_score = -1.0

        for name, record in self._records.items():
            score = float(np.dot(embedding, record.embedding))
            if score > best_score:
                best_score = score
                best_name = name

        if best_name and best_score >= self._threshold:
            return (best_name, best_score)

        return None

    def remove(self, name: str) -> bool:
        """Remove a person from the gallery."""
        with self._lock:
            if name not in self._records:
                return False

            del self._records[name]
            self._rebuild_index()
            print(f"[FaceGallery] Removed '{name}'")
            return True

    def list_persons(self) -> list[dict]:
        """List all enrolled persons with metadata."""
        return [
            {
                "name": r.name,
                "num_images": r.num_images,
                "created_at": r.created_at,
                "last_seen": r.last_seen,
                "match_count": r.match_count,
            }
            for r in self._records.values()
        ]

    def save(self, path: str):
        """Save gallery to JSON file."""
        os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)

        data = {
            "dim": self._dim,
            "threshold": self._threshold,
            "persons": {},
        }

        for name, record in self._records.items():
            data["persons"][name] = {
                "embedding": record.embedding.tolist(),
                "num_images": record.num_images,
                "created_at": record.created_at,
                "last_seen": record.last_seen,
                "match_count": record.match_count,
            }

        with open(path, "w") as f:
            json.dump(data, f, indent=2)

        print(f"[FaceGallery] Saved {len(self._records)} persons to {path}")

    def load(self, path: str) -> bool:
        """Load gallery from JSON file."""
        if not os.path.exists(path):
            print(f"[FaceGallery] No gallery file at {path}")
            return False

        with open(path, "r") as f:
            data = json.load(f)

        self._dim = data.get("dim", self._dim)
        self._threshold = data.get("threshold", self._threshold)

        self._records.clear()
        self._id_map.clear()
        if self._index is not None:
            self._index.reset()

        for name, person_data in data.get("persons", {}).items():
            embedding = np.array(person_data["embedding"], dtype=np.float32)
            record = PersonRecord(
                name=name,
                embedding=embedding,
                num_images=person_data.get("num_images", 1),
                created_at=person_data.get("created_at", time.time()),
                last_seen=person_data.get("last_seen", time.time()),
                match_count=person_data.get("match_count", 0),
            )
            self._records[name] = record

            if self._index is not None:
                self._index.add(embedding.reshape(1, -1).astype(np.float32))
                self._id_map.append(name)

        print(f"[FaceGallery] Loaded {len(self._records)} persons from {path}")
        return True

    def _rebuild_index(self):
        """Rebuild FAISS index from all records."""
        if self._index is None:
            return

        self._index.reset()
        self._id_map = []

        for name, record in self._records.items():
            self._index.add(record.embedding.reshape(1, -1).astype(np.float32))
            self._id_map.append(name)

    def get_embedding(self, name: str) -> Optional[np.ndarray]:
        """Get stored embedding for a person."""
        record = self._records.get(name)
        return record.embedding.copy() if record else None

    def set_threshold(self, threshold: float):
        """Update the matching threshold."""
        self._threshold = threshold
        print(f"[FaceGallery] Threshold set to {threshold}")
