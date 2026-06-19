"""
Multi-Model Ensemble Face Embedding.

Combines multiple face recognition models for maximum accuracy:
1. InsightFace buffalo_l (ArcFace-R100) - 512-dim
2. FaceNet VGGFace2 (InceptionResnetV1) - 512-dim

Combined embedding: 1024-dim for much stronger matching.
"""

import os
import numpy as np
from typing import Optional, List
import cv2

try:
    import insightface
    from insightface.app import FaceAnalysis
    HAS_INSIGHTFACE = True
except ImportError:
    HAS_INSIGHTFACE = False

try:
    from facenet_pytorch import InceptionResnetV1
    import torch
    HAS_FACENET = True
except ImportError:
    HAS_FACENET = False


def enhance_face(face_img: np.ndarray, target_size: int = 240) -> np.ndarray:
    h, w = face_img.shape[:2]
    if h >= target_size and w >= target_size:
        return face_img
    scale = target_size / min(h, w)
    return cv2.resize(face_img, (int(w * scale), int(h * scale)),
                      interpolation=cv2.INTER_CUBIC)


def face_in_bbox(face_bbox, person_bbox, margin=0.15):
    fx1, fy1, fx2, fy2 = face_bbox
    px1, py1, px2, py2 = person_bbox
    w = px2 - px1
    h = py2 - py1
    mx = w * margin
    my = h * margin
    cx = (fx1 + fx2) / 2
    cy = (fy1 + fy2) / 2
    return (px1 - mx <= cx <= px2 + mx) and (py1 - my <= cy <= py2 + my)


def normalize(arr):
    norm = np.linalg.norm(arr)
    if norm > 0:
        return arr / norm
    return arr


class MultiModelEmbedder:
    """
    Ensemble face embedder using InsightFace + FaceNet.

    Produces a combined 1024-dim embedding for maximum accuracy.
    Falls back to single model if one fails.
    """

    # Each model produces 512-dim, combined = 1024-dim
    EMBEDDING_DIM = 1024
    MIN_DET_SCORE = 0.15

    def __init__(self, device_id: int = 0):
        self._insight_app = None
        self._insight_app_large = None
        self._facenet = None
        self._device_id = device_id
        self._loaded = False

    def load(self):
        """Load all models."""
        if not HAS_INSIGHTFACE:
            raise ImportError("insightface required")
        if not HAS_FACENET:
            raise ImportError("facenet-pytorch required")

        print("[MultiModel] Loading InsightFace 640...")
        self._insight_app = FaceAnalysis(
            name="buffalo_l",
            providers=["CUDAExecutionProvider", "CPUExecutionProvider"],
        )
        self._insight_app.prepare(ctx_id=self._device_id, det_size=(640, 640))

        print("[MultiModel] Loading InsightFace 960...")
        self._insight_app_large = FaceAnalysis(
            name="buffalo_l",
            providers=["CUDAExecutionProvider", "CPUExecutionProvider"],
        )
        self._insight_app_large.prepare(ctx_id=self._device_id, det_size=(960, 960))

        print("[MultiModel] Loading FaceNet VGGFace2...")
        self._facenet = InceptionResnetV1(
            pretrained="vggface2",
            device="cpu",
        ).eval()

        self._loaded = True
        print("[MultiModel] All models loaded (InsightFace + FaceNet)")

    def _facenet_embed(self, face_img: np.ndarray) -> Optional[np.ndarray]:
        """Extract FaceNet embedding from a face image."""
        if self._facenet is None:
            return None
        try:
            # Resize to 160x160 (FaceNet input)
            resized = cv2.resize(face_img, (160, 160), interpolation=cv2.INTER_AREA)
            # BGR -> RGB -> tensor
            rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
            tensor = torch.from_numpy(rgb).permute(2, 0, 1).unsqueeze(0).float() / 255.0
            with torch.no_grad():
                emb = self._facenet(tensor).squeeze().numpy()
            return normalize(emb.astype(np.float32))
        except Exception:
            return None

    def _insightface_embed(self, face_img: np.ndarray) -> Optional[np.ndarray]:
        """Extract InsightFace embedding from a face image."""
        if self._insight_app is None:
            return None
        try:
            faces = self._insight_app.get(face_img)
            if not faces:
                faces = self._insight_app_large.get(face_img)
            if faces:
                best = max(faces, key=lambda f: f.det_score)
                if best.det_score >= self.MIN_DET_SCORE:
                    return normalize(best.normed_embedding.astype(np.float32))
        except Exception:
            pass
        return None

    def _combined_embed(self, face_img: np.ndarray) -> Optional[np.ndarray]:
        """Get combined 1024-dim embedding from both models."""
        emb_insight = self._insightface_embed(face_img)
        emb_facenet = self._facenet_embed(face_img)

        parts = []
        if emb_insight is not None:
            parts.append(emb_insight)
        if emb_facenet is not None:
            parts.append(emb_facenet)

        if not parts:
            return None

        # If only one model worked, use just that one (pad with zeros for the other half)
        if len(parts) == 1:
            if emb_insight is not None:
                return np.concatenate([emb_insight, np.zeros(512, dtype=np.float32)])
            else:
                return np.concatenate([np.zeros(512, dtype=np.float32), emb_facenet])

        # Both models worked - concatenate for 1024-dim
        combined = np.concatenate([emb_insight, emb_facenet])
        return normalize(combined)

    def detect_faces(self, frame: np.ndarray) -> list:
        """Detect ALL faces in frame with combined embeddings."""
        if not self._loaded:
            raise RuntimeError("Models not loaded.")

        all_faces = []

        # Run InsightFace at both scales to find faces
        for app in [self._insight_app, self._insight_app_large]:
            try:
                faces = app.get(frame)
                for f in faces:
                    if f.det_score >= self.MIN_DET_SCORE:
                        bbox = f.bbox.tolist()
                        # Check duplicate
                        is_dup = any(face_in_bbox(bbox, existing["bbox"]) for existing in all_faces)
                        if not is_dup:
                            # Extract face crop for FaceNet
                            fx1, fy1, fx2, fy2 = [int(max(0, v)) for v in f.bbox]
                            h, w = frame.shape[:2]
                            fx2, fy2 = min(w, fx2), min(h, fy2)
                            face_crop = frame[fy1:fy2, fx1:fx2]

                            # Combined embedding
                            emb = self._combined_embed(face_crop)
                            if emb is not None:
                                all_faces.append({
                                    "bbox": bbox,
                                    "det_score": float(f.det_score),
                                    "embedding": emb,
                                })
            except Exception:
                continue

        # Enhanced detection for tiny faces
        h, w = frame.shape[:2]
        if min(h, w) >= 100:
            enhanced = enhance_face(frame, target_size=320)
            scale_x = w / enhanced.shape[1]
            scale_y = h / enhanced.shape[0]
            try:
                faces = self._insight_app.get(enhanced)
                for f in faces:
                    if f.det_score >= self.MIN_DET_SCORE:
                        fb = f.bbox
                        real_bbox = [fb[0]*scale_x, fb[1]*scale_y, fb[2]*scale_x, fb[3]*scale_y]
                        is_dup = any(face_in_bbox(real_bbox, existing["bbox"]) for existing in all_faces)
                        if not is_dup:
                            fx1, fy1, fx2, fy2 = [int(max(0, v)) for v in f.bbox]
                            eh, ew = enhanced.shape[:2]
                            fx2, fy2 = min(ew, fx2), min(eh, fy2)
                            face_crop = enhanced[fy1:fy2, fx1:fx2]
                            emb = self._combined_embed(face_crop)
                            if emb is not None:
                                all_faces.append({
                                    "bbox": real_bbox,
                                    "det_score": float(f.det_score),
                                    "embedding": emb,
                                })
            except Exception:
                pass

        return all_faces

    def extract(self, frame: np.ndarray, bbox: dict = None) -> Optional[np.ndarray]:
        """Extract face embedding. If bbox given, match face to person."""
        if not self._loaded:
            raise RuntimeError("Models not loaded.")

        if bbox is None:
            faces = self.detect_faces(frame)
            if faces:
                return max(faces, key=lambda f: f["det_score"])["embedding"]
            return None

        # Match face to person bbox
        person_box = [bbox["x1"], bbox["y1"], bbox["x2"], bbox["y2"]]
        all_faces = self.detect_faces(frame)
        matches = [f for f in all_faces if face_in_bbox(f["bbox"], person_box)]

        if matches:
            return max(matches, key=lambda f: f["det_score"])["embedding"]

        # Fallback: crop-based
        return self._extract_from_crop(frame, bbox)

    def _extract_from_crop(self, frame: np.ndarray, bbox: dict) -> Optional[np.ndarray]:
        """Fallback: crop face and extract."""
        x1 = max(0, int(bbox["x1"]))
        y1 = max(0, int(bbox["y1"]))
        x2 = min(frame.shape[1], int(bbox["x2"]))
        y2 = min(frame.shape[0], int(bbox["y2"]))
        h = y2 - y1
        w = x2 - x1

        face_y2 = y1 + int(h * 0.45)
        face_y1 = max(0, y1 - int(h * 0.05))
        pad = int(w * 0.15)
        fx1 = max(0, x1 - pad)
        fx2 = min(frame.shape[1], x2 + pad)

        crop = frame[face_y1:face_y2, fx1:fx2]
        if crop.size == 0:
            return None

        ch, cw = crop.shape[:2]
        if min(ch, cw) < 20:
            crop = enhance_face(crop, target_size=240)

        return self._combined_embed(crop)

    def extract_batch(self, frame: np.ndarray, bboxes: list) -> list:
        """Batch extract: detect faces once, match to bboxes."""
        all_faces = self.detect_faces(frame)
        results = []
        for bbox in bboxes:
            person_box = [bbox["x1"], bbox["y1"], bbox["x2"], bbox["y2"]]
            matches = [f for f in all_faces if face_in_bbox(f["bbox"], person_box)]
            if matches:
                results.append(max(matches, key=lambda f: f["det_score"])["embedding"])
            else:
                results.append(self._extract_from_crop(frame, bbox))
        return results

    @staticmethod
    def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
        return float(np.dot(a, b))

    @staticmethod
    def average_embeddings(embeddings: list) -> np.ndarray:
        valid = [e for e in embeddings if e is not None]
        if not valid:
            return np.zeros(MultiModelEmbedder.EMBEDDING_DIM, dtype=np.float32)
        avg = np.mean(valid, axis=0).astype(np.float32)
        norm = np.linalg.norm(avg)
        if norm > 0:
            avg = avg / norm
        return avg


# Backward compat alias
FaceEmbedder = MultiModelEmbedder
