# without_reid — Zone-Based Hen Counting (Image Mode)

Lightweight multi-camera poultry counting pipeline using YOLOv11x detection. Processes **all images** from each camera folder, counts hens per image, and sums results. MiewID appearance embeddings used **only** at predefined overlap zones for cross-camera deduplication — no full ReID gallery.

## Architecture

```
main.py              Entry point, pipeline orchestration, CLI
overlap_dedup.py     MiewID-based deduplication with greedy clustering
roi_selector.py      Interactive GUI for drawing polygon ROIs
zone_counter.py      Multi-line crossing detector (reserved for future use)
```

## Pipeline

1. **ROI** — Polygon mask per camera (normalized 0-1, drawn via `--setup` GUI)
2. **Detection** — YOLOv11x (COCO class 14: bird) at confidence ≥ 0.35
3. **Filter** — Min box area 400px², max aspect ratio 3.0, ROI containment
4. **NMS** — Non-Maximum Suppression at IoU ≥ 0.45 to remove redundant boxes
5. **Count** — Detections summed per image, totals per camera
6. **Overlap dedup** (optional `--miewid`) — MiewID embeddings extracted only in overlap zones; greedy clustering matches same hen across cameras; duplicates subtracted
7. **Final count** = Σ per_camera_counts − overlap_duplicates

## Setup

### Folder Structure

Place images in camera directories. The pipeline loads **all** image files from each folder:

```
AI_MODEL__/
├── CH_01/
│   ├── image1.jpg        ← processed
│   ├── image2.jpg        ← processed
│   └── image3.png        ← processed
├── CH_02/
│   ├── cam02_shot1.jpg   ← processed
│   └── cam02_shot2.jpg   ← processed
├── CH_03/
│   └── ...
├── CH_04/
│   └── ...
├── CH_06/
│   └── ...
└── without_reid/
    ├── main.py
    ├── roi_selector.py
    ├── overlap_dedup.py
    ├── zone_counter.py
    └── roi_config.json   ← auto-generated after --setup
```

Supported formats: `.jpg`, `.jpeg`, `.png`, `.bmp`, `.tiff`

## Usage

```bash
# Step 1: Draw ROIs for each camera (one time setup)
python main.py --setup

# Step 2: Run detection on all images
python main.py

# Run headless (no OpenCV windows)
python main.py --no-gui

# Enable MiewID overlap dedup
python main.py --miewid

# Custom detection params
python main.py --conf 0.3 --nms-iou 0.5

# Combined: lower threshold, tighter NMS
python main.py --conf 0.25 --nms-iou 0.35
```

## ROI Setup

1. Run `python main.py --setup`
2. For each camera, the first image is displayed
3. **Left-click** to add polygon points around the counting zone
4. **Right-click** or **Enter** to close the polygon (minimum 3 points)
5. Press **n** for next camera, **s** to skip, **q** to quit and save
6. ROIs are saved to `roi_config.json`

## Files

| File | Purpose |
|------|---------|
| `main.py` | Pipeline entry point, camera discovery, YOLO detection, NMS, counting, reporting |
| `roi_selector.py` | `ROISelector` GUI (mouse callback, normalized coordinate storage) |
| `overlap_dedup.py` | `MiewIDExtractor` (timm EfficientNetV2 + GeM + BN), `OverlapZone`, `OverlapDeduplicator` with greedy clustering |
| `zone_counter.py` | `ZoneBasedCounter` + `CountingLine` + `HenTrack` (reserved for future use) |
| `__init__.py` | Package marker |

## Configuration

| Field | Default | CLI flag | Description |
|-------|---------|----------|-------------|
| `conf_threshold` | 0.35 | `--conf` | Detection confidence minimum |
| `nms_iou_threshold` | 0.45 | `--nms-iou` | NMS intersection-over-union threshold |
| `min_box_area` | 400 | — | Minimum bounding box area (px²) |
| `max_aspect_ratio` | 3.0 | — | Maximum width/height ratio |
| `max_detect_res` | 1280 | — | Longest side after resize |
| `bird_class_id` | 14 | — | COCO bird class |
| `overlap_threshold` | 0.65 | — | MiewID cosine similarity threshold |

## CLI Reference

```
--setup       Launch ROI selector GUI before running
--no-gui      Run headless (no OpenCV display)
--miewid      Enable MiewID overlap deduplication
--conf FLOAT  Detection confidence threshold
--nms-iou FLOAT  NMS IoU threshold (0.0-1.0)
```

## Output

Results printed to console and saved to `count_report.json`:

```json
{
  "config": "YOLOv11x image detection + MiewID overlap",
  "elapsed_s": 2.45,
  "total_images": 10,
  "per_camera": {
    "CH_01": { "count": 25, "total_dets": 25, "images": 3 },
    "CH_02": { "count": 18, "total_dets": 18, "images": 2 },
    "CH_03": { "count": 30, "total_dets": 30, "images": 3 },
    "CH_06": { "count": 12, "total_dets": 12, "images": 2 }
  },
  "raw_total": 85,
  "overlap_duplicates": 5,
  "final_count": 80
}
```
