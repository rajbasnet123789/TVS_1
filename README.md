# Poultry Monitoring System

AI-powered chicken monitoring with real-time detection via **Frigate NVR**, cross-camera re-identification (MiewID + FAISS), health classification, and web dashboard.

## Architecture

- **Backend:** Python FastAPI + SQLAlchemy (GPU inference pipeline)
- **Frontend:** React + TypeScript + Vite + Material UI
- **Databases:** PostgreSQL (relational), InfluxDB (time-series), Redis (cache/pub-sub), and Local File Storage (for media)
- **NVR + Detection:** Frigate (motion-triggered bird detection, go2rtc HLS streaming)
- **AI:** Frigate built-in detector (OpenVINO/TensorRT) + HealthClassifier (best.pt, 32 health classes) + MiewID (2152-dim ReID) + FAISS gallery for cross-camera identity matching

## Quick Start

### Docker (recommended) — all models included

```bash
docker compose up -d --build
```

This builds the backend image with:
- Frigate 0.17 for motion detection, bird detection, recording, and HLS streaming
- HealthClassifier model (best.pt) for fine-grained health analysis
- MiewID ReID model (200MB, pre-cached) for cross-camera chicken identity
- PyTorch with CUDA for GPU-accelerated health inference

Then open http://localhost:3000 and login with `admin@poultry.farm` and the password set in `DEFAULT_ADMIN_PASSWORD`.

### Local development (manual model setup)

See [docs/localhost-development-guide.md](docs/localhost-development-guide.md).

## Large Model Files (not in git)

| File | Size | Location | Used By |
|------|------|----------|---------|
| `best.pt` | ~25 MB | `AI_MODEL__/AI_MODEL/best.pt` | Backend health classification |
| `yolov8x.pt` | 130 MB | `yolov8x.pt` | AI_MODEL standalone tests |
| `yolov8m.pt` | 50 MB | `yolov8m.pt` | Fallback detection model |
| `yolo11n.pt` | 5 MB | `AI_MODEL__/model 2/yolo11n.pt` | Fecal disease model |

### Download Health Model

```bash
# Place your trained best.pt in:
AI_MODEL__/AI_MODEL/best.pt
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
│   │   ├── botsort_custom.yaml
│   │   └── dataset/       # Training data (not in git)
│   └── model 2/           # Fecal disease model
├── backend/               # FastAPI REST API + WebSocket
│   ├── Dockerfile         # CUDA + models baked in
│   └── app/
│       ├── frigate/       # Frigate integration
│       │   ├── subscriber.py  # MQTT event → health + MCMT pipeline
│       │   ├── client.py      # Frigate REST API client
│       │   ├── config_manager.py  # Camera config generator
│       │   └── schemas.py
│       ├── detection/
│       │   ├── detector.py      # HealthClassifier (best.pt)
│       │   ├── mcmt_singleton.py # Shared GlobalTracker
│       │   └── queries.py       # InfluxDB queries
│       ├── cameras/        # Camera CRUD + ONVIF scan
│       ├── auth/           # Auth + impersonation
│       ├── alerts/         # Alert rules + evaluation
│       ├── health/         # Health score queries
│       ├── websocket/      # Real-time push
│       └── media/          # MinIO upload/download
├── frontend/              # React dashboard
│   └── Dockerfile         # Nginx + Vite build
├── frigate/               # Frigate config directory
├── mosquitto/             # MQTT broker config
├── docs/                  # Architecture + deployment docs
├── docker-compose.yml     # Full stack orchestration
└── .env.example           # Environment template
```

## GPU Requirements

- **CUDA 12.4+** with NVIDIA GPU (tested on RTX 3050 Laptop 4GB)
- **VRAM**: ~1-2 GB during inference (HealthClassifier + MiewID)
- Falls back to CPU if CUDA unavailable (slower)
- Frigate can also use OpenVINO (Intel GPU/CPU) for detection
- Docker uses `nvidia-container-toolkit` for GPU passthrough

### Docker GPU Setup

Requires [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html):

```bash
# Ubuntu/Debian
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
  sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
  sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
```

### Useful Docker Commands

```bash
# Build with GPU
docker compose up -d --build

# View backend logs
docker compose logs -f backend

# View Frigate logs
docker compose logs -f frigate

# Rebuild only backend
docker compose build backend && docker compose up -d backend

# Stop all
docker compose down

# Stop and remove volumes (fresh start)
docker compose down -v
```

## Documentation

- [Architecture Document](docs/architecture.md)
- [Deployment Guide](docs/deployment_guide.md)
- [Localhost Development Guide](docs/localhost-development-guide.md)
