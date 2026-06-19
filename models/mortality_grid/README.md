# MortalityGrid — Rule-Based Mortality Detection

Grid-based system for detecting dead birds in dense broiler flocks from CCTV video.

## Overview

This is **not a trained ML model** — it is a deterministic rule-based algorithm that overlays a coarse grid (35px cells) on the camera view and tracks each cell's state over time to distinguish dead birds from sleeping/resting birds.

## Algorithm

### Grid Cell State Machine

```
ACTIVE ──→ SUSPECT_STATIC ──→ DEAD_CANDIDATE ──→ CONFIRMED_DEAD
   ↑              │                   │
   └──────────────┴───────────────────┘
         (on movement detected)
```

| State | Meaning |
|-------|---------|
| `ACTIVE` | Movement detected in cell |
| `SUSPECT_STATIC` | No movement for threshold duration |
| `DEAD_CANDIDATE` | Persisted static beyond threshold, passed flush events |
| `CONFIRMED_DEAD` | Verified after 24h cooldown |

### Key Mechanisms

- **Static duration tracking**: Each cell tracks how long no centroid has moved within it
- **Natural flush detection**: When a large fraction of cells become active simultaneously (e.g., birds shifting), static cells that remain unmoved are promoted to candidates
- **Debouncing**: Configurable frame count to ignore brief pauses
- **Aspect ratio stability**: Dead birds have near-zero bbox variance (< 1.5 px)
- **24h verification**: Candidates only confirm after a full day cycle

## Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `cell_size` | 35 px | Grid cell side length |
| `static_threshold_min` | 30.0 min | Minutes of no movement → SUSPECT_STATIC |
| `movement_threshold_px` | 10.0 px | Centroid displacement threshold |
| `flush_threshold` | 0.7 | Fraction of cells active to trigger flush |
| `auto_escalation_hours` | 3.0 hrs | Auto-promote static cells after this |
| `debounce_frames` | 15 | Frames to wait before flagging static |

## Usage

```python
from mortality_grid import MortalityGrid

# Full-frame grid
grid = MortalityGrid(roi_bbox=(0, 0, frame_w, frame_h))
grid.static_threshold_min = 30.0

for frame in video:
    dets = [(x1, y1, x2, y2, conf), ...]   # from YOLO
    changes = grid.update(dets, timestamp)

    if grid.detect_natural_flush(timestamp):
        grid.process_flush(timestamp)

    confirmed = grid.confirm_deaths(timestamp)

    report = grid.rollup_daily()
    print(f"Confirmed dead: {report['confirmed_dead']['count']}")
```

## Source Code

The implementation lives in `mortality_grid.py` at the project root (614 lines). It is imported by `_run_0007.py` and `_run_35px_test.py` for testing on video 0007.mp4.

## Dependencies

- Python 3.8+
- NumPy
- No ML frameworks required
