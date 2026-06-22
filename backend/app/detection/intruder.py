import os
import json
import time
import logging
import threading
import numpy as np
import cv2
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)

# Optional dependencies logic
try:
    import insightface
    from insightface.app import FaceAnalysis
    HAS_INSIGHTFACE = True
except ImportError:
    HAS_INSIGHTFACE = False

try:
    import torch
    from facenet_pytorch import InceptionResnetV1
    HAS_FACENET = True
except ImportError:
    HAS_FACENET = False

try:
    import faiss
    HAS_FAISS = True
except ImportError:
    HAS_FAISS = False


def enhance_face(face_img: np.ndarray, target_size: int = 240) -> np.ndarray:
    h, w = face_img.shape[:2]
    if h >= target_size and w >= target_size:
        return face_img
    scale = target_size / min(h, w)
    return cv2.resize(face_img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_CUBIC)


def face_in_bbox(face_bbox, person_bbox, margin=0.15):
    fx1, fy1, fx2, fy2 = face_bbox
    px1, py1, px2, py2 = person_bbox
    w = px2 - px1
    h = py2 - py1
    mx = w * margin
    my = h * margin
    cx = (fx1 + fx2) / 2
    cy = (fy1 + fy2) / 2
    return (px1 - mx <= cx <= px2 + mx) and (px1 - my <= cy <= px2 + my)


def normalize(arr: np.ndarray) -> np.ndarray:
    norm = np.linalg.norm(arr)
    if norm > 0:
        return arr / norm
    return arr


class FaceEmbedder:
    """Ensemble face embedding extraction using InsightFace (ArcFace-R100) + FaceNet."""
    EMBEDDING_DIM = 1024
    MIN_DET_SCORE = 0.15

    def __init__(self, device_id: int = 0):
        self._insight_app = None
        self._insight_app_large = None
        self._facenet = None
        self._device_id = device_id
        self._loaded = False

    def load(self):
        if self._loaded:
            return
        if not HAS_INSIGHTFACE:
            raise ImportError("insightface is required for FaceEmbedder")
        if not HAS_FACENET:
            raise ImportError("facenet-pytorch/torch is required for FaceEmbedder")

        logger.info("Loading InsightFace FaceAnalysis (det_size=640)...")
        self._insight_app = FaceAnalysis(
            name="buffalo_l",
            providers=["CUDAExecutionProvider", "CPUExecutionProvider"],
        )
        self._insight_app.prepare(ctx_id=self._device_id, det_size=(640, 640))

        logger.info("Loading InsightFace FaceAnalysis (det_size=960)...")
        self._insight_app_large = FaceAnalysis(
            name="buffalo_l",
            providers=["CUDAExecutionProvider", "CPUExecutionProvider"],
        )
        self._insight_app_large.prepare(ctx_id=self._device_id, det_size=(960, 960))

        logger.info("Loading FaceNet InceptionResnetV1 (vggface2)...")
        self._facenet = InceptionResnetV1(
            pretrained="vggface2",
            device="cpu",
        ).eval()

        self._loaded = True
        logger.info("FaceEmbedder models successfully loaded")

    def _facenet_embed(self, face_img: np.ndarray) -> Optional[np.ndarray]:
        if self._facenet is None:
            return None
        try:
            resized = cv2.resize(face_img, (160, 160), interpolation=cv2.INTER_AREA)
            rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
            tensor = torch.from_numpy(rgb).permute(2, 0, 1).unsqueeze(0).float() / 255.0
            with torch.no_grad():
                emb = self._facenet(tensor).squeeze().numpy()
            return normalize(emb.astype(np.float32))
        except Exception as e:
            logger.warning(f"FaceNet embedding failed: {e}")
            return None

    def _insightface_embed(self, face_img: np.ndarray) -> Optional[np.ndarray]:
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
        except Exception as e:
            logger.warning(f"InsightFace embedding failed: {e}")
        return None

    def _combined_embed(self, face_img: np.ndarray) -> Optional[np.ndarray]:
        emb_insight = self._insightface_embed(face_img)
        emb_facenet = self._facenet_embed(face_img)

        parts = []
        if emb_insight is not None:
            parts.append(emb_insight)
        if emb_facenet is not None:
            parts.append(emb_facenet)

        if not parts:
            return None

        if len(parts) == 1:
            if emb_insight is not None:
                return np.concatenate([emb_insight, np.zeros(512, dtype=np.float32)])
            else:
                return np.concatenate([np.zeros(512, dtype=np.float32), emb_facenet])

        combined = np.concatenate([emb_insight, emb_facenet])
        return normalize(combined)

    def detect_faces(self, frame: np.ndarray) -> list[dict]:
        if not self._loaded:
            self.load()

        all_faces = []
        for app in [self._insight_app, self._insight_app_large]:
            try:
                faces = app.get(frame)
                for f in faces:
                    if f.det_score >= self.MIN_DET_SCORE:
                        bbox = f.bbox.tolist()
                        is_dup = any(face_in_bbox(bbox, existing["bbox"]) for existing in all_faces)
                        if not is_dup:
                            fx1, fy1, fx2, fy2 = [int(max(0, v)) for v in f.bbox]
                            h, w = frame.shape[:2]
                            fx2, fy2 = min(w, fx2), min(h, fy2)
                            face_crop = frame[fy1:fy2, fx1:fx2]
                            if face_crop.size > 0:
                                emb = self._combined_embed(face_crop)
                                if emb is not None:
                                    all_faces.append({
                                        "bbox": bbox,
                                        "det_score": float(f.det_score),
                                        "embedding": emb,
                                    })
            except Exception as e:
                logger.warning(f"Error during FaceAnalysis frame processing: {e}")
                continue

        # Tiny face handler
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
                            if face_crop.size > 0:
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

    def extract(self, frame: np.ndarray, bbox: Optional[dict] = None) -> Optional[np.ndarray]:
        if not self._loaded:
            self.load()

        if bbox is None:
            faces = self.detect_faces(frame)
            if faces:
                return max(faces, key=lambda f: f["det_score"])["embedding"]
            return None

        # Match face to person bbox
        person_box = [bbox["x"], bbox["y"], bbox["x"] + bbox["w"], bbox["y"] + bbox["h"]]
        all_faces = self.detect_faces(frame)
        matches = [f for f in all_faces if face_in_bbox(f["bbox"], person_box)]

        if matches:
            return max(matches, key=lambda f: f["det_score"])["embedding"]

        # Fallback to upper 40% bbox crop
        return self._extract_from_crop(frame, bbox)

    def _extract_from_crop(self, frame: np.ndarray, bbox: dict) -> Optional[np.ndarray]:
        x1 = max(0, int(bbox["x"]))
        y1 = max(0, int(bbox["y"]))
        x2 = min(frame.shape[1], int(bbox["x"] + bbox["w"]))
        y2 = min(frame.shape[0], int(bbox["y"] + bbox["h"]))
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


class FaceGallery:
    """FAISS-based Face embedding storage and similarity search gallery."""
    def __init__(self, embedding_dim: int = 1024, match_threshold: float = 0.3):
        self._dim = embedding_dim
        self._threshold = match_threshold
        self._records: dict[str, dict] = {}
        self._lock = threading.Lock()

        if HAS_FAISS:
            self._index = faiss.IndexFlatIP(embedding_dim)
            self._id_map: list[str] = []
        else:
            self._index = None
            self._id_map = []
            logger.warning("FAISS not available. Falling back to brute-force NumPy similarity.")

    @property
    def threshold(self) -> float:
        return self._threshold

    @threshold.setter
    def threshold(self, val: float):
        self._threshold = val

    def add(self, name: str, embedding: np.ndarray, num_images: int = 1):
        with self._lock:
            if name in self._records:
                record = self._records[name]
                alpha = 0.3
                updated = alpha * embedding + (1 - alpha) * np.array(record["embedding"], dtype=np.float32)
                norm = np.linalg.norm(updated)
                if norm > 0:
                    updated = updated / norm
                record["embedding"] = updated.tolist()
                record["num_images"] += num_images
                record["last_seen"] = time.time()
                record["match_count"] += 1
            else:
                self._records[name] = {
                    "name": name,
                    "embedding": embedding.tolist(),
                    "num_images": num_images,
                    "created_at": time.time(),
                    "last_seen": time.time(),
                    "match_count": 0,
                }
            self._rebuild_index()

    def search(self, embedding: np.ndarray) -> Optional[tuple[str, float]]:
        if not self._records:
            return None

        with self._lock:
            if self._index is not None and self._index.ntotal > 0:
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
            else:
                # NumPy Cosine Similarity brute-force search
                best_name = None
                best_score = -1.0
                for name, record in self._records.items():
                    score = float(np.dot(embedding, np.array(record["embedding"], dtype=np.float32)))
                    if score > best_score:
                        best_score = score
                        best_name = name
                if best_name and best_score >= self._threshold:
                    return (best_name, best_score)

        return None

    def remove(self, name: str) -> bool:
        with self._lock:
            if name not in self._records:
                return False
            del self._records[name]
            self._rebuild_index()
            return True

    def list_persons(self) -> list[dict]:
        with self._lock:
            return [
                {
                    "name": r["name"],
                    "num_images": r["num_images"],
                    "created_at": r["created_at"],
                    "last_seen": r["last_seen"],
                    "match_count": r["match_count"],
                }
                for r in self._records.values()
            ]

    def save(self, path: str):
        with self._lock:
            os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
            data = {
                "dim": self._dim,
                "threshold": self._threshold,
                "persons": self._records,
            }
            with open(path, "w") as f:
                json.dump(data, f, indent=2)

    def load(self, path: str) -> bool:
        if not os.path.exists(path):
            return False
        try:
            with open(path, "r") as f:
                data = json.load(f)
            self._dim = data.get("dim", self._dim)
            self._threshold = data.get("threshold", self._threshold)
            with self._lock:
                self._records = data.get("persons", {})
                self._rebuild_index()
            return True
        except Exception as e:
            logger.error(f"Failed to load FaceGallery from {path}: {e}")
            return False

    def _rebuild_index(self):
        if self._index is None:
            return
        self._index.reset()
        self._id_map = []
        for name, record in self._records.items():
            emb = np.array(record["embedding"], dtype=np.float32)
            self._index.add(emb.reshape(1, -1).astype(np.float32))
            self._id_map.append(name)


class IntruderDetector:
    """Wrapper singleton for embedding generation, matching, and gallery state management."""
    def __init__(self):
        self._embedder = None
        self._galleries = {}
        self._lock = threading.Lock()

    def load(self):
        with self._lock:
            if self._embedder is not None:
                return
            self._embedder = FaceEmbedder()
            try:
                self._embedder.load()
            except Exception as e:
                logger.error(f"Failed to load FaceEmbedder: {e}")
            self._galleries = {}

    def get_gallery(self, farm_id: str) -> FaceGallery:
        if self._embedder is None:
            self.load()
        farm_id_str = str(farm_id) if farm_id else '00000000-0000-0000-0000-000000000001'
        with self._lock:
            if farm_id_str not in self._galleries:
                gallery = FaceGallery(embedding_dim=FaceEmbedder.EMBEDDING_DIM, match_threshold=settings.intruder_threshold)
                base_dir = os.path.dirname(settings.face_gallery_path)
                filename = os.path.basename(settings.face_gallery_path)
                farm_gallery_path = os.path.join(
                    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")),
                    base_dir,
                    f"farm_{farm_id_str}",
                    filename
                )
                gallery.load(farm_gallery_path)
                self._galleries[farm_id_str] = gallery
            return self._galleries[farm_id_str]

    @property
    def gallery(self) -> FaceGallery:
        # Fallback to default farm for backward compatibility or when farm_id is not specified
        return self.get_gallery('00000000-0000-0000-0000-000000000001')

    def extract_embedding(self, frame: np.ndarray, bbox: Optional[dict] = None) -> Optional[np.ndarray]:
        if self._embedder is None:
            self.load()
        try:
            return self._embedder.extract(frame, bbox)
        except Exception as e:
            logger.warning(f"Failed to extract face embedding: {e}")
            return None

    def verify_face(self, frame: np.ndarray, farm_id: str, bbox: Optional[dict] = None) -> Optional[tuple[str, float]]:
        emb = self.extract_embedding(frame, bbox)
        if emb is None:
            return None
        gallery = self.get_gallery(farm_id)
        return gallery.search(emb)

    def enroll_person(self, name: str, frame: np.ndarray, farm_id: str) -> bool:
        emb = self.extract_embedding(frame)
        if emb is None:
            return False
        gallery = self.get_gallery(farm_id)
        gallery.add(name, emb)
        
        base_dir = os.path.dirname(settings.face_gallery_path)
        filename = os.path.basename(settings.face_gallery_path)
        farm_gallery_path = os.path.join(
            os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")),
            base_dir,
            f"farm_{str(farm_id)}",
            filename
        )
        gallery.save(farm_gallery_path)
        return True

    def remove_person(self, name: str, farm_id: str) -> bool:
        gallery = self.get_gallery(farm_id)
        removed = gallery.remove(name)
        if removed:
            base_dir = os.path.dirname(settings.face_gallery_path)
            filename = os.path.basename(settings.face_gallery_path)
            farm_gallery_path = os.path.join(
                os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")),
                base_dir,
                f"farm_{str(farm_id)}",
                filename
            )
            gallery.save(farm_gallery_path)
        return removed


intruder_detector = IntruderDetector()
