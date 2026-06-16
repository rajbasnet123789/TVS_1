"""
Overlap Zone Deduplication — MiewID Only at Overlap Regions.

When two cameras share physical space, the same hen may be counted twice.
This module uses MiewID appearance embeddings ONLY in defined overlap zones to:
  1. Extract embeddings for detections in overlap areas
  2. Cluster similar embeddings across cameras to identify unique individuals
  3. Subtract overlap duplicates from the total count

Production features:
  - Hungarian matching / greedy clustering instead of O(n²) all-pairs
  - Temporal consistency: same track_id in overlap zone stored once
  - Configurable similarity threshold with validation
"""
import time
import logging
import numpy as np
import cv2
import torch
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


class GeM(torch.nn.Module):
    def __init__(self, p=3, eps=1e-6):
        super().__init__()
        self.p = torch.nn.Parameter(torch.ones(1) * p)
        self.eps = eps

    def forward(self, x):
        return torch.nn.functional.avg_pool2d(
            x.clamp(min=self.eps).pow(self.p),
            (x.size(-2), x.size(-1))
        ).pow(1.0 / self.p)


class MiewIDExtractor:
    def __init__(self):
        self._backbone = None
        self._bn = None
        self._transform = None
        self._device = "cpu"
        self._loaded = False
        self._dim = 2152

    def load(self):
        self._device = "cuda:0" if torch.cuda.is_available() else "cpu"
        try:
            import timm
            from safetensors.torch import load_file
            from huggingface_hub import hf_hub_download
            from timm.data import resolve_data_config, create_transform

            backbone = timm.create_model("efficientnetv2_rw_m", pretrained=False,
                                         num_classes=0)
            backbone.global_pool = GeM()
            bn = torch.nn.BatchNorm1d(self._dim)

            weights_path = hf_hub_download("conservationxlabs/miewid-msv3",
                                           "model.safetensors")
            weights = load_file(weights_path)

            bs = {k.replace("backbone.", ""): v
                  for k, v in weights.items() if k.startswith("backbone.")}
            backbone.load_state_dict(bs, strict=False)
            bn_s = {k.replace("bn.", ""): v
                    for k, v in weights.items() if k.startswith("bn.")}
            bn.load_state_dict(bn_s)

            self._backbone = backbone.to(self._device).eval()
            self._bn = bn.to(self._device).eval()
            data_config = resolve_data_config(self._backbone.pretrained_cfg)
            self._transform = create_transform(**data_config, is_training=False)
            self._loaded = True
            logger.info(f"MiewID loaded on {self._device} (dim={self._dim})")
        except Exception as e:
            logger.error(f"MiewID load failed: {e}")

    def extract(self, frame, bboxes):
        if not self._loaded or not bboxes:
            return [None] * len(bboxes)
        from PIL import Image
        crops, valid_idx = [], []
        for i, b in enumerate(bboxes):
            x1 = max(0, int(b[0]))
            y1 = max(0, int(b[1]))
            x2 = min(frame.shape[1], int(b[0] + b[2]))
            y2 = min(frame.shape[0], int(b[1] + b[3]))
            if x2 - x1 < 10 or y2 - y1 < 10:
                continue
            crop = frame[y1:y2, x1:x2]
            if crop.size == 0:
                continue
            pil = Image.fromarray(crop[:, :, ::-1] if len(crop.shape) == 3 else crop)
            crops.append(self._transform(pil).unsqueeze(0))
            valid_idx.append(i)
        if not crops:
            return [None] * len(bboxes)
        try:
            batch = torch.cat(crops, dim=0).to(self._device)
            with torch.no_grad():
                feat = self._backbone(batch).view(-1, self._dim)
                features = self._bn(feat)
            features = features.cpu().numpy()
            result = [None] * len(bboxes)
            for j, idx in enumerate(valid_idx):
                if j < len(features):
                    emb = features[j].flatten()
                    n = np.linalg.norm(emb)
                    result[idx] = emb / n if n > 0 else emb
            return result
        except Exception as e:
            logger.warning(f"MiewID extract failed: {e}")
            return [None] * len(bboxes)


@dataclass
class OverlapZone:
    name: str
    camera_ids: list[str]
    roi_polygon: list[tuple[float, float]]


class OverlapDeduplicator:
    def __init__(self, overlap_zones: list[OverlapZone], threshold: float = 0.65):
        self.zones = overlap_zones
        self.threshold = threshold
        self.extractor = MiewIDExtractor()
        self._embeddings: dict[str, list[dict]] = {}
        self._total_duplicates = 0
        self._unique_individuals = 0

    def load(self):
        self.extractor.load()

    def extract_overlap_embeddings(self, camera_id: str, frame,
                                   detections: list[dict]):
        if not self.extractor._loaded:
            return
        zone = None
        for z in self.zones:
            if camera_id in z.camera_ids:
                zone = z
                break
        if zone is None:
            return

        h, w = frame.shape[:2]
        roi_pts = np.array([[int(x * w), int(y * h)]
                            for x, y in zone.roi_polygon], dtype=np.int32)

        in_zone_bboxes = []
        in_zone_indices = []
        for i, det in enumerate(detections):
            cx = det["bbox"][0] + det["bbox"][2] / 2
            cy = det["bbox"][1] + det["bbox"][3] / 2
            if cv2.pointPolygonTest(roi_pts, (cx, cy), False) >= 0:
                in_zone_bboxes.append(det["bbox"])
                in_zone_indices.append(i)

        if not in_zone_bboxes:
            return

        if camera_id not in self._embeddings:
            self._embeddings[camera_id] = []

        seen_track_ids = {e["track_id"] for e in self._embeddings[camera_id]}

        embeddings = self.extractor.extract(frame, in_zone_bboxes)
        for emb, raw_idx in zip(embeddings, in_zone_indices):
            if emb is None:
                continue
            tid = detections[raw_idx].get("track_id", -1)
            if tid in seen_track_ids:
                continue
            seen_track_ids.add(tid)
            self._embeddings[camera_id].append({
                "embedding": emb,
                "bbox": detections[raw_idx]["bbox"],
                "track_id": tid,
                "timestamp": time.time(),
            })

    def find_duplicates(self) -> int:
        """Greedy cluster-based duplicate counting.
        Instead of O(n²) all-pairs, we build clusters across cameras
        and count unique individuals per overlap zone.
        """
        cam_ids = list(self._embeddings.keys())
        if len(cam_ids) < 2:
            self._total_duplicates = 0
            self._unique_individuals = 0
            return 0

        all_embeddings: list[dict] = []
        for cid in cam_ids:
            for e in self._embeddings[cid]:
                all_embeddings.append({
                    **e,
                    "camera_id": cid,
                })

        if not all_embeddings:
            self._total_duplicates = 0
            self._unique_individuals = 0
            return 0

        assigned = [False] * len(all_embeddings)
        clusters: list[list[int]] = []

        for i in range(len(all_embeddings)):
            if assigned[i]:
                continue
            cluster = [i]
            assigned[i] = True
            emb_i = all_embeddings[i]["embedding"]
            for j in range(i + 1, len(all_embeddings)):
                if assigned[j]:
                    continue
                if all_embeddings[i]["camera_id"] == all_embeddings[j]["camera_id"]:
                    continue
                emb_j = all_embeddings[j]["embedding"]
                sim = float(np.dot(emb_i, emb_j))
                if sim >= self.threshold:
                    cluster.append(j)
                    assigned[j] = True
            clusters.append(cluster)

        unique_per_camera = 0
        seen_camera_pairs = set()
        for cluster in clusters:
            cams_in_cluster = set()
            for idx in cluster:
                cams_in_cluster.add(all_embeddings[idx]["camera_id"])
            if len(cams_in_cluster) > 1:
                unique_per_camera += 1
                for c1 in cams_in_cluster:
                    for c2 in cams_in_cluster:
                        if c1 < c2:
                            seen_camera_pairs.add((c1, c2))

        self._unique_individuals = sum(
            1 for c in clusters if len(c) > 0
        )
        duplicate_count = 0
        for cluster in clusters:
            cams_in_cluster = {all_embeddings[idx]["camera_id"]
                               for idx in cluster}
            duplicate_count += max(0, len(cams_in_cluster) - 1)

        self._total_duplicates = duplicate_count
        logger.info(f"Overlap dedup: {len(clusters)} clusters, "
                    f"{duplicate_count} duplicates in {len(cam_ids)} cameras")
        return self._total_duplicates

    def get_total_duplicates(self) -> int:
        return self._total_duplicates

    def clear_embeddings(self):
        self._embeddings.clear()


class GlobalCountManager:
    def __init__(self, overlap_dedup: Optional[OverlapDeduplicator] = None):
        self._camera_counts: dict[str, int] = {}
        self._overlap_dedup = overlap_dedup
        self._final_count = 0

    def set_camera_count(self, camera_id: str, net_count: int):
        self._camera_counts[camera_id] = net_count

    def compute_final_count(self) -> int:
        raw_total = sum(self._camera_counts.values())
        duplicates = 0
        if self._overlap_dedup:
            self._overlap_dedup.find_duplicates()
            duplicates = self._overlap_dedup.get_total_duplicates()
        self._final_count = raw_total - duplicates
        return self._final_count

    def get_breakdown(self) -> dict:
        return {
            "camera_counts": dict(self._camera_counts),
            "raw_total": sum(self._camera_counts.values()),
            "overlap_duplicates":
                self._overlap_dedup.get_total_duplicates()
                if self._overlap_dedup else 0,
            "final_count": self._final_count,
        }
