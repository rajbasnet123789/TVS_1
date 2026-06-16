"""
YOLOv11 + P2 + Transformer ReID Model Configuration

Custom modules for small object detection and cross-camera identification:

- ghost_modules: GhostConv, C3Ghost, C2fGhost for lightweight deployment
- transformer_reid: ViT-based ReID for long-range identification
- msfn_head: Multi-Scale Feed-forward Network for enhanced detection
- global_id_manager: Coordinate fusion for multi-camera tracking
"""

from .ghost_modules import GhostConv, C3Ghost, C2fGhost, GhostBottleneck
from .transformer_reid import TransformerReIDExtractor, ViTReID
from .msfn_head import MSFNDetectionHead, ScaleAggregation
from .global_id_manager import GlobalIDManager, CoordinateFusion

__all__ = [
    "GhostConv", "C3Ghost", "C2fGhost", "GhostBottleneck",
    "TransformerReIDExtractor", "ViTReID",
    "MSFNDetectionHead", "ScaleAggregation",
    "GlobalIDManager", "CoordinateFusion",
]
