# Poultry Monitoring System

AI-powered chicken monitoring with real-time detection, re-identification, health analysis, and web dashboard.

## Architecture

- **Backend:** Python FastAPI + SQLAlchemy + Celery (GPU inference)
- **Frontend:** React + TypeScript + Vite + Material UI
- **Databases:** PostgreSQL (relational), InfluxDB (time-series), Redis (cache/pub-sub), MinIO (object storage)
- **Media:** MediaMTX for RTSP → HLS conversion
- **AI:** YOLOv8x (1280px) + MiewID (2152-dim ReID) + FAISS gallery for cross-camera identity matching

## Quick Start

```bash
docker compose up -d
```

Then open http://localhost:3000 and login with `admin@poultry.farm` / `admin123`.

## Large Model Files (not in git)

Model weights are excluded from git via `.gitignore`. Place them manually at the paths below:

| File | Size | Location | Used By |
|------|------|----------|---------|
| `yolov8x.pt` | 130 MB | `AI_MODEL__/AI_MODEL/yolov8x.pt` | Backend detection (YOLOv8x) |
| `yolov8x.pt` | 130 MB | `yolov8x.pt` | AI_MODEL standalone tests |
| `yolov8m.pt` | 50 MB | `yolov8m.pt` | Fallback detection model |
| `yolov8l.pt` | 84 MB | `AI_MODEL__/AI_MODEL/yolov8l.pt` | Previous model (optional) |
| `yolo11n.pt` | 5 MB | `AI_MODEL__/model 2/yolo11n.pt` | Fecal disease model |

### Download YOLOv8x

```bash
# Option 1: Ultralytics auto-download (first run auto-downloads to CWD)
python -c "from ultralytics import YOLO; YOLO('yolov8x.pt')"

# Option 2: Manual download from GitHub releases
curl -L -o yolov8x.pt https://github.com/ultralytics/assets/releases/download/v8.2.0/yolov8x.pt
```

### ReID Models (auto-downloaded)

ReID models download automatically on first run:

- **MiewID** (`conservationxlabs/miewid-msv3`): `~/.cache/huggingface/hub/models--conservationxlabs--miewid-msv3/` (~200MB)
- **OSNet** (fallback): `~/.cache/torch/hub/checkpoints/osnet_x0_25_msmt17.pt` (~10MB)

No manual setup needed for ReID models.

## Project Structure

```
D:\TVS_1\
├── AI_MODEL__/            # AI model code + training data
│   ├── AI_MODEL/
│   │   ├── main.py        # Standalone detection entry
│   │   ├── mcmt_test.py   # MCMT system test
│   │   ├── hen_counter.py # Hen counter orchestrator
│   │   ├── reid.py        # Zone-based counting
│   │   ├── yolov8x.pt     # ← PLACE MODEL HERE (130MB)
│   │   ├── botsort_custom.yaml
│   │   └── dataset/       # Training data (not in git)
│   └── model 2/           # Fecal disease model
├── backend/               # FastAPI REST API + WebSocket
│   └── app/detection/
│       ├── detector.py    # YOLOv8x + SAHI tiling
│       ├── tracker.py     # BoT-SORT single-camera
│       └── mcmt/          # Multi-camera multi-target
│           ├── embeddings.py  # MiewID/OSNet ReID
│           ├── gallery.py     # FAISS vector search
│           └── tracker.py     # Global identity tracking
├── frontend/              # React dashboard
├── docs/                  # Architecture docs
├── docker-compose.yml
├── mediamtx.yml
└── yolov8x.pt             # ← ALSO PLACE HERE (130MB)
```

## GPU Requirements

- **CUDA 11.8+** with NVIDIA GPU (tested on RTX 3050 Laptop 4GB)
- **VRAM**: ~2-3 GB during inference (YOLOv8x + MiewID)
- Falls back to CPU if CUDA unavailable (slower)

## Documentation

- [Architecture Document](docs/architecture.md)
- [Localhost Development Guide](docs/localhost-development-guide.md)
