# TVS Poultry Monitor

AI-powered, multi-farm poultry monitoring system. Live chicken counts from IP/NVR cameras, real-time alerts, and a company-level dashboard for managing every farm from one place.

- **Detection:** Custom `cv_engine/` service — YOLOv8 + OpenCV + FFmpeg, count-only (no per-chicken identity tracking)
- **Video:** [go2rtc](https://github.com/AlexxIT/go2rtc) relays NVR channels and serves HLS at `:1984` (host network); the dashboard is count-first
- **Backend:** Python FastAPI + SQLAlchemy (single worker)
- **Frontend:** React + TypeScript + Vite + Material UI, served by nginx (which also reverse-proxies the API)
- **Data:** PostgreSQL (relational), InfluxDB (time-series detections), Redis (sessions/blacklist), local filesystem for media
- **Multi-farm:** Farm-scoped data isolation + super admin who can manage all farms and impersonate any user

## Quick Start (Docker)

```bash
cp .env.example .env      # fill in secrets (see .env.example comments)
docker compose up -d --build
```

Then open **http://localhost:3001** and log in with `admin@poultry.farm` (password = `DEFAULT_ADMIN_PASSWORD` in `.env`).

> Local development without Docker: see [docs/localhost-development-guide.md](docs/localhost-development-guide.md).

## Architecture in One Paragraph

IP cameras / an NVR publish RTSP streams. **go2rtc** (host network) ingests them and re-exposes clean HLS endpoints. The **cv-engine** (host network, GPU) reads the RTSP streams with FFmpeg, runs YOLOv8 to count chickens per frame, and writes detection counts to InfluxDB (with a `farm_id` tag). The **backend** reads those counts back and serves them as REST + WebSocket to the **frontend**. The frontend renders per-camera count cards on a shared 3-second poll. See [docs/architecture.md](docs/architecture.md) for the full picture.

## Services & Ports

| Service    | Host port | Purpose |
|------------|-----------|---------|
| frontend   | 3001      | Web UI (nginx serves the SPA and proxies `/api/` + `/ws`) |
| backend    | 18000     | FastAPI REST + WebSocket (container port 8000) |
| cv-engine  | 8700      | YOLO detection pipeline (host network, GPU) |
| go2rtc     | 1984 / 8554 | HLS API / RTSP relay (host network) |
| postgres   | 5433      | Relational database |
| influxdb   | 8086      | Time-series detection data |
| redis      | 6379      | Cache, token blacklist |
| mosquitto  | 1883      | MQTT broker (reserved for future use) |

## Project Structure

```
├── backend/               # FastAPI REST API + WebSocket
│   ├── app/
│   │   ├── api/v1/        # Route wiring incl. /v1/internal/*
│   │   ├── auth/          # Auth, JWT, impersonation, deletion requests
│   │   ├── farms/         # Multi-farm CRUD + farm scoping
│   │   ├── cameras/       # Camera CRUD, ONVIF scan
│   │   ├── chickens/      # Chicken records
│   │   ├── coops/         # Coop/group management
│   │   ├── detection/     # Counts/history/summary from InfluxDB
│   │   ├── alerts/        # Alert CRUD + rule evaluator (60s interval)
│   │   ├── analytics/     # Analytics endpoints
│   │   ├── environment/   # Environmental telemetry (IoT-ready)
│   │   ├── health/        # Health score queries (populated once health ML lands)
│   │   ├── media/         # Local-filesystem media CRUD (farm-scoped)
│   │   ├── nvr/           # NVR connect/discover/register (Dahua CGI + ONVIF)
│   │   ├── xmeye/         # XMEye LAN camera discovery
│   │   ├── websocket/     # /ws — farm-scoped realtime channel
│   │   └── alerts/rules.py# Alert rule evaluator (sole owner)
│   └── alembic/           # DB migrations (001_mcmt → 005)
├── cv_engine/             # YOLOv8 + OpenCV + FFmpeg pipeline (subprocess per camera)
│   ├── server.py          # FastAPI: camera sync loop, health/status, xmeye scan
│   ├── camera_manager.py  # Per-camera subprocess manager
│   ├── camera_worker.py   # FFmpeg + YOLOv8 + frame store per camera
│   ├── stream_manager.py  # RTSP→JPEG frame extraction
│   ├── influx_writer.py   # Detection queue → InfluxDB
│   └── box_processor.py   # YOLO output → count boxes
├── frontend/              # React dashboard (Vite + MUI), nginx.conf proxies
├── go2rtc/                # go2rtc config — static NVR channel streams
├── mosquitto/             # MQTT broker config
├── models/                # ML model metadata + weights
├── docs/                  # Architecture, deployment, dev guides
├── docker-compose.yml     # Full stack
├── docker-compose.prod.yml# Production overrides
└── .env.example           # Environment template
```

## Key Features

- **Multi-farm:** each farm has isolated cameras, chickens, users, alerts, settings. Super admin (`admin@poultry.farm`) manages all farms from one dashboard via a farm switcher.
- **Impersonation:** super admin can view the app as any user for 15 minutes (yellow banner with Stop button).
- **Live counts:** per-camera chicken counts from YOLO, refreshed on a shared 3s poll.
- **Video relay:** go2rtc ingests all NVR channels and exposes HLS at `http://<host>:1984` — handy for ad-hoc viewing; embedding it in the dashboard is a roadmap item.
- **Alert rules:** configurable rules (inactivity, headcount drop, missing camera, etc.) evaluated every 60s with deduplication.
- **Privacy & compliance:** public privacy policy at `/privacy-policy`, in-app account/data deletion requests (Settings → Delete Account & Data), single-sign-on support (Google OAuth).
- **Automated backups:** daily `pg_dump` + InfluxDB backup with 14-day retention.

## Documentation

- [Architecture](docs/architecture.md)
- [Deployment](docs/deployment_guide.md)
- [Server Runbook & Updates](deployment.md)
- [Localhost Development Guide](docs/localhost-development-guide.md)
- [Contributing](CONTRIBUTING.md)
- [Changelog](CHANGELOG.md)
- [TODO list](TODOS.md)

## GPU Requirements

- NVIDIA GPU with CUDA (tested on RTX 3050, 4 GB VRAM) and the [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html).
- `cv-engine` runs with `runtime: nvidia` and CUDA + FP16; the backend runs on CPU.
- Falls back to CPU if no GPU is available (slower).
