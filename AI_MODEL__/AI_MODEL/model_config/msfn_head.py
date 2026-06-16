"""
Multi-Scale Feed-forward Network (MSFN) for YOLO detection head.

MSFN enhances small object detection by processing features at multiple
scales within the detection head itself. Combined with the P2 layer,
this provides significant improvement for long-range hen detection.

Architecture:
- Multi-scale feature aggregation from P2, P3, P4, P5
- Cross-scale attention for feature fusion
- Enhanced detection head for small objects
"""

import torch
import torch.nn as nn
import torch.nn.functional as F


class ScaleAttention(nn.Module):
    """Cross-scale attention for multi-scale feature fusion."""

    def __init__(self, channels, num_scales=4):
        super().__init__()
        self.scale_weights = nn.Parameter(torch.ones(num_scales) / num_scales)
        self.norm = nn.LayerNorm(channels)

    def forward(self, features_list):
        weights = F.softmax(self.scale_weights, dim=0)
        aligned = []
        target_h, target_w = features_list[0].shape[2], features_list[0].shape[3]

        for i, feat in enumerate(features_list):
            if feat.shape[2] != target_h or feat.shape[3] != target_w:
                feat = F.adaptive_avg_pool2d(feat, (target_h, target_w))
            aligned.append(feat * weights[i])

        fused = torch.stack(aligned, dim=0).sum(dim=0)
        B, C, H, W = fused.shape
        fused = fused.permute(0, 2, 3, 1).reshape(-1, C)
        fused = self.norm(fused)
        fused = fused.reshape(B, H, W, C).permute(0, 3, 1, 2)
        return fused


class ScaleAggregation(nn.Module):
    """Aggregates features from multiple FPN scales."""

    def __init__(self, c_p2=64, c_p3=128, c_p4=256, c_p5=512, out_channels=128):
        super().__init__()
        self.lateral_p2 = nn.Conv2d(c_p2, out_channels, 1)
        self.lateral_p3 = nn.Conv2d(c_p3, out_channels, 1)
        self.lateral_p4 = nn.Conv2d(c_p4, out_channels, 1)
        self.lateral_p5 = nn.Conv2d(c_p5, out_channels, 1)

        self.smooth_p2 = nn.Conv2d(out_channels, out_channels, 3, padding=1)

        self.attention = ScaleAttention(out_channels, num_scales=4)

        self.fusion_conv = nn.Sequential(
            nn.Conv2d(out_channels, out_channels, 3, padding=1, bias=False),
            nn.BatchNorm2d(out_channels),
            nn.SiLU(inplace=True),
            nn.Conv2d(out_channels, out_channels, 3, padding=1, bias=False),
            nn.BatchNorm2d(out_channels),
            nn.SiLU(inplace=True),
        )

    def forward(self, features):
        p2, p3, p4, p5 = features

        p2_lat = self.lateral_p2(p2)
        p3_lat = self.lateral_p3(p3)
        p4_lat = self.lateral_p4(p4)
        p5_lat = self.lateral_p5(p5)

        fused = self.attention([p2_lat, p3_lat, p4_lat, p5_lat])
        out = self.smooth_p2(fused + p2_lat)
        out = self.fusion_conv(out)
        return out


class MSFNDetectionHead(nn.Module):
    """
    Multi-Scale Feed-forward Network Detection Head.

    Replaces standard YOLO detection head with multi-scale processing
    for improved small object detection at long ranges.
    """

    def __init__(self, num_classes=1, in_channels_list=(64, 128, 256, 512), reg_max=16):
        super().__init__()
        self.num_classes = num_classes
        self.reg_max = reg_max
        self.num_outputs = num_classes + reg_max * 4

        self.aggregation = ScaleAggregation(
            c_p2=in_channels_list[0],
            c_p3=in_channels_list[1],
            c_p4=in_channels_list[2],
            c_p5=in_channels_list[3],
            out_channels=128,
        )

        cls_dim = 128
        reg_dim = 128

        self.cls_conv = nn.Sequential(
            nn.Conv2d(cls_dim, cls_dim, 3, padding=1, bias=False),
            nn.BatchNorm2d(cls_dim),
            nn.SiLU(inplace=True),
            nn.Conv2d(cls_dim, cls_dim, 3, padding=1, bias=False),
            nn.BatchNorm2d(cls_dim),
            nn.SiLU(inplace=True),
        )
        self.cls_pred = nn.Conv2d(cls_dim, num_classes, 1)

        self.reg_conv = nn.Sequential(
            nn.Conv2d(reg_dim, reg_dim, 3, padding=1, bias=False),
            nn.BatchNorm2d(reg_dim),
            nn.SiLU(inplace=True),
            nn.Conv2d(reg_dim, reg_dim, 3, padding=1, bias=False),
            nn.BatchNorm2d(reg_dim),
            nn.SiLU(inplace=True),
        )
        self.reg_pred = nn.Conv2d(reg_dim, 4 * reg_max, 1)
        self.obj_pred = nn.Conv2d(reg_dim, 1, 1)

        self._init_bias()

    def _init_bias(self):
        for s, p_in in zip([128], [64]):
            conv = self.cls_pred
            b = conv.bias
            if b is not None:
                b.data.fill_(-np.log(0.75 / (1 - 0.75) / (self.num_classes * 64 * 64)))
            conv = self.obj_pred
            b = conv.bias
            if b is not None:
                b.data.fill_(-np.log(0.75 / (1 - 0.75)))

    def forward(self, features):
        fused = self.aggregation(features)

        cls_feat = self.cls_conv(fused)
        cls_output = self.cls_pred(cls_feat)

        reg_feat = self.reg_conv(fused)
        reg_output = self.reg_pred(reg_feat)
        obj_output = self.obj_pred(reg_feat)

        return cls_output, reg_output, obj_output


import numpy as np
