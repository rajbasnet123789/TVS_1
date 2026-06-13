# Poultry Monitoring System

AI-powered chicken monitoring with real-time detection, re-identification, health analysis, and web dashboard.

## Architecture

- **Backend:** Python FastAPI + SQLAlchemy + Celery (GPU inference)
- **Frontend:** React + TypeScript + Vite + Material UI
- **Databases:** PostgreSQL (relational), InfluxDB (time-series), Redis (cache/pub-sub), MinIO (object storage)
- **Media:** MediaMTX for RTSP → HLS conversion
- **AI:** YOLOv8n two-stage pipeline (detection + re-identification)

## Quick Start

```bash
docker compose up -d
```

Then open http://localhost:3000 and login with `admin@poultry.farm` / `admin123`.

## Project Structure

```
A:\TVS_1\
├── AI_MODEL/            # Model training (separate project)
├── backend/             # FastAPI REST API + WebSocket
├── frontend/            # React dashboard
├── docs/                # Architecture docs + guides
├── docker-compose.yml   # Service orchestration
├── mediamtx.yml         # Media server config
└── .env.example         # Environment template
```

## Documentation

- [Architecture Document](docs/architecture.md)
- [Localhost Development Guide](docs/localhost-development-guide.md)
- [Phase 1 Implementation Plan](docs/phase1-implementation-plan.md)
