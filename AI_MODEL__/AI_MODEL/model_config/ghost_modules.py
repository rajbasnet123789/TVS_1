"""
Lightweight model modules: GhostConv, C3Ghost, C2fGhost.

GhostConv reduces parameters by using cheap linear operations to generate
ghost feature maps from a small set of intrinsic features. C3Ghost applies
this within the CSP bottleneck structure for efficient feature fusion.
"""

import torch
import torch.nn as nn


class GhostConv(nn.Module):
    """Ghost Convolution: generates cheap linear transformed feature maps."""

    def __init__(self, c1, c2, k=1, s=1, g=1, act=True):
        super().__init__()
        c_ = c2 // 2
        self.cv1 = nn.Conv2d(c1, c_, k, s, k // 2, groups=g, bias=False)
        self.bn1 = nn.BatchNorm2d(c_)
        self.act1 = nn.SiLU(inplace=True) if act else nn.Identity()
        self.cv2 = nn.Conv2d(c_, c_, 5, 1, 2, groups=c_, bias=False)
        self.bn2 = nn.BatchNorm2d(c_)

    def forward(self, x):
        y = self.act1(self.bn1(self.cv1(x)))
        return torch.cat([y, self.bn2(self.cv2(y))], 1)


class GhostBottleneck(nn.Module):
    """Ghost bottleneck block for efficient feature transformation."""

    def __init__(self, c1, c2, k=3, s=1, e=2):
        super().__init__()
        c_ = int(c2 * e)
        self.ghost1 = GhostConv(c1, c_, 1, 1)
        self.ghost2 = GhostConv(c_, c2, k, s)
        self.shortcut = (
            nn.Sequential(
                nn.Conv2d(c1, c1, k, s, k // 2, groups=c1, bias=False),
                nn.BatchNorm2d(c1),
                nn.Conv2d(c1, c2, 1, 1, bias=False),
                nn.BatchNorm2d(c2),
            )
            if s != 1 or c1 != c2
            else nn.Identity()
        )

    def forward(self, x):
        residual = self.shortcut(x)
        return self.ghost2(self.ghost1(x)) + residual


class C3Ghost(nn.Module):
    """CSP Bottleneck with 3 convolutions using GhostConv."""

    def __init__(self, c1, c2, n=1, g=1, e=0.5):
        super().__init__()
        c_ = int(c2 * e)
        self.cv1 = nn.Conv2d(c1, c_, 1, 1, bias=False)
        self.cv2 = nn.Conv2d(c1, c_, 1, 1, bias=False)
        self.cv3 = Conv(2 * c_, c2, 1, 1, bias=False)
        self.m = nn.Sequential(
            *[GhostBottleneck(c_, c_, 3, 1) for _ in range(n)]
        )
        self.bn = nn.BatchNorm2d(2 * c_)
        self.act = nn.SiLU(inplace=True)

    def forward(self, x):
        return self.cv3(self.act(self.bn(torch.cat((self.m(self.cv1(x)), self.cv2(x)), 1))))


class C2fGhost(nn.Module):
    """Faster GhostCSP with 2 convolutions."""

    def __init__(self, c1, c2, n=1, g=1, e=0.5):
        super().__init__()
        self.c = int(c2 * e)
        self.cv1 = Conv(c1, 2 * self.c, 1, 1)
        self.cv2 = Conv((2 + n) * self.c, c2, 1)
        self.m = nn.ModuleList(
            [GhostBottleneck(self.c, self.c, 3, 1) for _ in range(n)]
        )

    def forward(self, x):
        y = list(self.cv1(x).chunk(2, 1))
        y.extend(m(y[-1]) for m in self.m)
        return self.cv2(torch.cat(y, 1))


class Conv(nn.Module):
    """Standard convolution block: Conv2d + BN + SiLU."""

    def __init__(self, c1, c2, k=1, s=1, p=None, g=1, act=True, bias=False):
        super().__init__()
        self.conv = nn.Conv2d(c1, c2, k, s, p or k // 2, groups=g, bias=bias)
        self.bn = nn.BatchNorm2d(c2)
        self.act = nn.SiLU(inplace=True) if act else nn.Identity()

    def forward(self, x):
        return self.act(self.bn(self.conv(x)))
