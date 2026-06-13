import logging
import os
import time
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

MIEWID_REPO = "conservationxlabs/miewid-msv3"
MIEWID_DIM = 2152


@dataclass
class HenIdentity:
    global_id: int
    embedding: np.ndarray
    last_camera_id: str
    last_seen: float = field(default_factory=time.time)
    first_seen: float = field(default_factory=time.time)
    camera_history: list[str] = field(default_factory=list)
    embedding_history: list[np.ndarray] = field(default_factory=list)
    total_detections: int = 1
    avg_confidence: float = 0.0


class EmbeddingExtractor:
    def __init__(self):
        self._backbone = None
        self._bn = None
        self._device = "cpu"
        self._backbone_name = None

    async def load(self):
        if self._backbone_name is not None:
            return

        self._device = "cuda:0" if __import__("torch").cuda.is_available() else "cpu"

        try:
            self._load_miewid()
            self._backbone_name = "miewid"
            logger.info(f"MiewID loaded on {self._device} (dim={MIEWID_DIM})")
            return
        except Exception as e:
            logger.warning(f"MiewID load failed: {e}")

        try:
            self._load_osnet()
            self._backbone_name = "osnet"
            logger.info(f"OSNet fallback loaded on {self._device}")
        except Exception as e:
            logger.warning(f"No ReID model available: {e}")

    def _load_miewid(self):
        import torch
        import timm
        import torch.nn as nn
        import torch.nn.functional as F
        from safetensors.torch import load_file
        from huggingface_hub import hf_hub_download

        class GeM(nn.Module):
            def __init__(self, p=3, eps=1e-6):
                super().__init__()
                self.p = nn.Parameter(torch.ones(1) * p)
                self.eps = eps

            def forward(self, x):
                return F.avg_pool2d(
                    x.clamp(min=self.eps).pow(self.p),
                    (x.size(-2), x.size(-1)),
                ).pow(1.0 / self.p)

        backbone = timm.create_model("efficientnetv2_rw_m", pretrained=False, num_classes=0)
        backbone.global_pool = GeM()
        bn = nn.BatchNorm1d(MIEWID_DIM)

        weights_path = hf_hub_download(MIEWID_REPO, "model.safetensors")
        weights = load_file(weights_path)

        backbone_state = {
            k.replace("backbone.", ""): v
            for k, v in weights.items()
            if k.startswith("backbone.")
        }
        backbone.load_state_dict(backbone_state, strict=False)

        bn_state = {k.replace("bn.", ""): v for k, v in weights.items() if k.startswith("bn.")}
        bn.load_state_dict(bn_state)

        self._backbone = backbone.to(self._device).eval()
        self._bn = bn.to(self._device).eval()

    def _load_osnet(self):
        import torch
        from boxmot.reid.core import ReID

        reid = ReID(device=self._device)
        self._backbone = reid.model
        self._bn = None

    def _preprocess_miewid(self, crop: np.ndarray):
        import torch
        from PIL import Image
        from timm.data import resolve_data_config, create_transform

        if crop.shape[0] == 0 or crop.shape[1] == 0:
            return None
        if not hasattr(self, "_transform"):
            data_config = resolve_data_config(self._backbone.pretrained_cfg)
            self._transform = create_transform(**data_config, is_training=False)
        pil = Image.fromarray(crop[:, :, ::-1] if crop.shape[2] == 3 else crop)
        return self._transform(pil).unsqueeze(0)

    def _preprocess_osnet(self, crop: np.ndarray):
        import torch
        import cv2

        resized = cv2.resize(crop, (64, 128), interpolation=cv2.INTER_LINEAR)
        pre = self._backbone.inference_preprocess(resized)
        t = torch.from_numpy(pre).float()
        if t.ndim == 3:
            t = t.permute(2, 0, 1).unsqueeze(0)
        return t.to(self._backbone.device)

    def extract(
        self,
        frame: np.ndarray,
        bboxes: list[dict],
    ) -> list[Optional[np.ndarray]]:
        if self._backbone_name is None or not bboxes:
            return [None] * len(bboxes)

        import torch

        crops = []
        valid_indices = []
        for i, bbox in enumerate(bboxes):
            x1 = max(0, int(bbox["x"]))
            y1 = max(0, int(bbox["y"]))
            x2 = min(frame.shape[1], int(bbox["x"] + bbox["w"]))
            y2 = min(frame.shape[0], int(bbox["y"] + bbox["h"]))

            if x2 - x1 < 10 or y2 - y1 < 10:
                continue

            crop = frame[y1:y2, x1:x2]
            if crop.size == 0:
                continue

            if self._backbone_name == "miewid":
                t = self._preprocess_miewid(crop)
            else:
                t = self._preprocess_osnet(crop)
            if t is None:
                continue

            crops.append(t)
            valid_indices.append(i)

        if not crops:
            return [None] * len(bboxes)

        try:
            batch = torch.cat(crops, dim=0).to(self._device)
            with torch.no_grad():
                if self._backbone_name == "miewid":
                    feat = self._backbone(batch)
                    feat = feat.view(feat.size(0), -1)
                    features = self._bn(feat)
                else:
                    features = self._backbone.model(batch)
            features = features.cpu().numpy()

            result = [None] * len(bboxes)
            for j, idx in enumerate(valid_indices):
                if j < len(features):
                    emb = features[j].flatten()
                    norm = np.linalg.norm(emb)
                    if norm > 0:
                        emb = emb / norm
                    result[idx] = emb
            return result
        except Exception as e:
            logger.warning(f"Embedding extraction failed: {e}")
            return [None] * len(bboxes)
