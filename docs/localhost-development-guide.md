# Poultry Monitoring System — Localhost Development Guide

## Prerequisites

- **Docker Desktop** (Windows/Mac) or **Docker Engine** (Linux)
- **NVIDIA Container Toolkit** (optional — skip for CPU-only mode)
- **Git**
- **Node.js 20+** (for frontend dev without Docker)
- **Python 3.11+** (for backend dev without Docker)

## Quick Start

```bash
# 1. Clone and enter the project
cd A:\TVS_1

# 2. Start all services
docker compose up -d

# 3. Access the application
#    Frontend: http://localhost:3000
#    Backend API: http://localhost:8000
#    API Docs: http://localhost:8000/docs
#    MediaMTX HLS: http://localhost:8888

# 4. Login with default credentials:
#    Email: admin@poultry.farm
#    Password: admin123
```

## Default Credentials

| Role | Email | Password |
|------|-------|----------|
| Super Admin | admin@poultry.farm | admin123 |

*Additional roles are created automatically. Register new users via the API at `/auth/register`.*

## Service Ports

| Service | Port | Purpose |
|---------|------|---------|
| Frontend | 3000 | React dashboard |
| Backend API | 8000 | FastAPI REST + WebSocket |
| PostgreSQL | 5432 | Relational database |
| Redis | 6379 | Cache + pub/sub + queue |
| InfluxDB | 8086 | Time-series metrics |
| MinIO | 9000 / 9001 | Object storage / Console |
| MediaMTX HLS | 8888 | HLS video streams |
| MediaMTX RTSP | 8554 | RTSP relay |
| MediaMTX API | 9997 | Stream management |

## Development Without Docker

### Backend
```bash
cd backend
python -m venv .venv
.venv\Scripts\activate  # Windows
pip install -e ".[dev]"

# Ensure postgres, redis, influxdb, minio are running (docker compose up -d postgres redis influxdb minio)
uvicorn app.main:app --reload --port 8000
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```

## Adding a Camera

1. Navigate to **Cameras** in the sidebar
2. Click **"Add Camera"** and enter the RTSP URL
3. Or click **"Scan Network"** to auto-discover ONVIF cameras
4. The camera will appear in the Dashboard and Live Feed

### Using a Mock Camera
If no real cameras are available, the backend can generate synthetic frames. Set a camera's RTSP URL to `mock://camera1` to use the mock generator.

## API Endpoints

| Method | Path | Auth | Permission |
|--------|------|------|------------|
| POST | /v1/auth/login | No | — |
| POST | /v1/auth/register | No | — |
| POST | /v1/auth/refresh | No | — |
| GET | /v1/auth/me | Yes | — |
| POST | /v1/auth/change-password | Yes | — |
| GET | /v1/auth/users | Yes | users:read |
| GET | /v1/cameras | Yes | cameras:read |
| GET | /v1/cameras/{id} | Yes | cameras:read |
| POST | /v1/cameras | Yes | cameras:write |
| PUT | /v1/cameras/{id} | Yes | cameras:write |
| DELETE | /v1/cameras/{id} | Yes | cameras:delete |
| POST | /v1/cameras/scan | Yes | cameras:scan |
| GET | /v1/cameras/scan/status | Yes | cameras:read |
| GET | /v1/cameras/scan/results | Yes | cameras:read |
| GET | /v1/chickens | Yes | chickens:read |
| GET | /v1/chickens/{id} | Yes | chickens:read |
| POST | /v1/chickens | Yes | chickens:write |
| PUT | /v1/chickens/{id} | Yes | chickens:write |
| DELETE | /v1/chickens/{id} | Yes | chickens:write |
| WS | /ws | Yes (token) | — |
| GET | /health | No | — |

## Testing

```bash
cd backend
pip install -e ".[dev]"
pytest -v
```

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Port conflict | Stop the service using the port, or change ports in docker-compose.yml |
| Backend can't connect to DB | Ensure postgres container is healthy first: `docker compose logs postgres` |
| Camera shows "Offline" | Check RTSP URL is correct, and the camera is reachable from the Docker host |
| HLS stream not loading | Verify MediaMTX is running: `curl http://localhost:9997/v2/paths/list` |
| ONVIF scan finds nothing | Ensure backend uses host network mode, and cameras are on the same subnet |
