"""
InsightFace ArcFace Embedding Extraction Module.

Extracts robust 512-dim face embeddings using InsightFace's ArcFace-R100
backbone (buffalo_l model). Handles face detection within person crops
and produces L2-normalized embeddings for cosine similarity matching.

Robustness techniques:
- Multi-angle enrollment with embedding averaging
- L2 normalization for cosine similarity via inner product
- Face quality filtering (confidence threshold)
- Fallback face region extraction when InsightFace detector fails
"""

import os
import numpy as np
from typing import Optional

try:
    import insightface
    from insightface.app import FaceAnalysis
    HAS_INSIGHTFACE = True
except ImportError:
    HAS_INSIGHTFACE = False


class FaceEmbedder:
    """
    ArcFace-based face embedding extractor using InsightFace.

    Pipeline:
    1. Receive person crop (background-removed from YOLO seg)
    2. InsightFace detects face within the crop
    3. ArcFace-R100 extracts 512-dim embedding
    4. L2-normalize for cosine similarity matching
    """

    EMBEDDING_DIM = 512

    def __init__(
        self,
        model_name: str = "buffalo_l",
        det_size: tuple = (640, 640),
        det_threshold: float = 0.5,
        device_id: int = 0,
    ):
        self._app = None
        self._model_name = model_name
        self._det_size = det_size
        self._det_threshold = det_threshold
        self._device_id = device_id
        self._loaded = False

    def load(self):
        """Load the InsightFace face analysis model."""
        if not HAS_INSIGHTFACE:
            raise ImportError(
                "insightface is required. Install with: "
                "pip install insightface onnxruntime"
            )

        self._app = FaceAnalysis(
            name=self._model_name,
            providers=["CUDAExecutionProvider", "CPUExecutionProvider"],
        )
        self._app.prepare(ctx_id=self._device_id, det_size=self._det_size)
        self._loaded = True
        print(f"[FaceEmbedder] Loaded InsightFace model '{self._model_name}' "
              f"(det_size={self._det_size})")

    def extract(self, frame: np.ndarray, bbox: dict = None) -> Optional[np.ndarray]:
        """
        Extract face embedding from a frame.

        Args:
            frame: BGR image (H, W, 3). Can be full frame or person crop.
            bbox: Optional bounding box {"x1", "y1", "x2", "y2"} to crop
                  face region before embedding. If None, processes full frame.

        Returns:
            L2-normalized 512-dim embedding, or None if no face detected.
        """
        if not self._loaded:
            raise RuntimeError("Model not loaded. Call load() first.")

        # Crop to bbox region if provided
        if bbox is not None:
            x1 = max(0, int(bbox["x1"]))
            y1 = max(0, int(bbox["y1"]))
            x2 = min(frame.shape[1], int(bbox["x2"]))
            y2 = min(frame.shape[0], int(bbox["y2"]))

            if x2 - x1 < 20 or y2 - y1 < 20:
                return None

            face_region = frame[y1:y2, x1:x2]
            if face_region.size == 0:
                return None
        else:
            face_region = frame

        # InsightFace face detection + embedding
        faces = self._app.get(face_region)

        if not faces:
            # Fallback: try extracting upper portion of person crop (face region)
            if bbox is not None:
                return self._fallback_face_extract(frame, bbox)
            return None

        # Pick the face with highest detection score
        best_face = max(faces, key=lambda f: f.det_score)

        if best_face.det_score < self._det_threshold:
            return None

        # Get embedding and L2-normalize
        embedding = best_face.normed_embedding.astype(np.float32)
        norm = np.linalg.norm(embedding)
        if norm > 0:
            embedding = embedding / norm

        return embedding

    def _fallback_face_extract(self, frame: np.ndarray, bbox: dict) -> Optional[np.ndarray]:
        """
        Fallback: extract face from upper 40% of person bounding box.
        Used when InsightFace face detector fails on the full person crop.
        """
        x1 = max(0, int(bbox["x1"]))
        y1 = max(0, int(bbox["y1"]))
        x2 = min(frame.shape[1], int(bbox["x2"]))
        y2 = min(frame.shape[0], int(bbox["y2"]))

        h = y2 - y1
        face_y2 = y1 + int(h * 0.4)

        if face_y2 - y1 < 20:
            return None

        face_region = frame[y1:face_y2, x1:x2]
        if face_region.size == 0:
            return None

        faces = self._app.get(face_region)
        if not faces:
            return None

        best_face = max(faces, key=lambda f: f.det_score)
        if best_face.det_score < self._det_threshold * 0.8:
            return None

        embedding = best_face.normed_embedding.astype(np.float32)
        norm = np.linalg.norm(embedding)
        if norm > 0:
            embedding = embedding / norm

        return embedding

    def extract_batch(
        self, frame: np.ndarray, bboxes: list[dict]
    ) -> list[Optional[np.ndarray]]:
        """
        Extract embeddings for multiple person detections.

        Args:
            frame: Full BGR frame.
            bboxes: List of bounding box dicts.

        Returns:
            List of embeddings (or None per detection).
        """
        return [self.extract(frame, bbox) for bbox in bboxes]

    @staticmethod
    def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
        """Compute cosine similarity between two L2-normalized vectors."""
        return float(np.dot(a, b))

    @staticmethod
    def average_embeddings(embeddings: list[np.ndarray]) -> np.ndarray:
        """
        Average multiple embeddings and re-normalize.
        Used during multi-sample enrollment for robustness.
        """
        valid = [e for e in embeddings if e is not None]
        if not valid:
            return np.zeros(FaceEmbedder.EMBEDDING_DIM, dtype=np.float32)

        avg = np.mean(valid, axis=0).astype(np.float32)
        norm = np.linalg.norm(avg)
        if norm > 0:
            avg = avg / norm
        return avg
