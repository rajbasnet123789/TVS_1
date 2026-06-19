"""
Whole-Body Appearance Embedder using ResNet18.

Extracts body features (clothing, shape, color) from person crops.
Works for far camera where faces are too small to recognize.
"""

import numpy as np
import cv2

try:
    import torch
    import torch.nn as nn
    from torchvision import models, transforms
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False


class BodyEmbedder:
    """
    Extracts 512-dim appearance features from whole person crops.

    Uses ResNet18 pretrained on ImageNet, strips final layer,
    produces feature vector that captures:
    - Clothing color and pattern
    - Body shape and proportions
    - Overall appearance
    """

    EMBEDDING_DIM = 512

    def __init__(self):
        self.model = None
        self.transform = None
        self._loaded = False

    def load(self):
        if not HAS_TORCH:
            raise ImportError("torch required")

        model = models.resnet18(pretrained=True)
        model = nn.Sequential(*list(model.children())[:-1])
        model.eval()

        self.model = model
        self.transform = transforms.Compose([
            transforms.ToPILImage(),
            transforms.Resize((128, 64)),
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406],
                                 std=[0.229, 0.224, 0.225]),
        ])
        self._loaded = True
        print("[BodyEmbedder] Loaded ResNet18 body feature extractor")

    def extract(self, person_crop):
        """
        Extract body appearance embedding from a person crop.

        Args:
            person_crop: BGR image of person (full body or upper body)

        Returns:
            L2-normalized 512-dim embedding.
        """
        if not self._loaded:
            raise RuntimeError("Not loaded")

        if person_crop is None or person_crop.size == 0:
            return None

        h, w = person_crop.shape[:2]
        if h < 10 or w < 10:
            return None

        # Convert BGR to RGB
        rgb = cv2.cvtColor(person_crop, cv2.COLOR_BGR2RGB)

        # Resize to standard body size (tall and narrow)
        resized = cv2.resize(rgb, (64, 128), interpolation=cv2.INTER_AREA)

        # Extract features
        tensor = self.transform(resized).unsqueeze(0)

        with torch.no_grad():
            features = self.model(tensor).squeeze().numpy()

        # L2 normalize
        features = features.astype(np.float32)
        norm = np.linalg.norm(features)
        if norm > 0:
            features = features / norm

        return features
