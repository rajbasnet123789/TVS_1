# Poultry Monitoring System — Localhost Development Guide

## Prerequisites

- **Docker Desktop** (Windows/Mac) or **Docker Engine** (Linux)
- **NVIDIA Container Toolkit** (optional — skip for CPU-only mode)
- **Git**
- **Node.js 20+** (for frontend dev without Docker)
- **Python 3.11+** (for backend dev without Docker)

## Quick Start

```bash
# 1. Start all services
docker compose up -d

# 2. Access the application
#    Frontend: http://localhost:3000
#    Backend API: http://localhost:8000
#    API Docs: http://localhost:8000/docs
#    Frigate UI: http://localhost:8971

# 3. Login with default credentials:
#    Email: admin@poultry.farm
#    Password: (set in DEFAULT_ADMIN_PASSWORD env var)
```

## Default Credentials

| Role | Email | Password |
|------|-------|----------|
| Super Admin | `admin@poultry.farm` | Check the value of the `DEFAULT_ADMIN_PASSWORD` variable in your `.env` file |

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
| Frigate API | 5000 | Frigate internal API |
| Frigate go2rtc | 1984 | HLS/WebRTC video streams |
| Frigate UI | 8971 | Frigate management UI |
| Mosquitto | 1883 | MQTT broker |
| Frigate RTSP | 8554 | RTSP relay (internal) |

## Development Without Docker

### Backend
```bash
cd backend
python -m venv .venv
.venv\Scripts\activate  # Windows
pip install -e ".[dev]"

# Ensure postgres, redis, influxdb, minio, mosquitto, frigate are running
# (docker compose up -d postgres redis influxdb minio mosquitto frigate)
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
3. The backend auto-registers the camera in Frigate via its API — Frigate handles motion detection, bird detection, and HLS streaming
4. The camera will appear in the Dashboard and Live Feed

## Key API Endpoints

| Method | Path | Auth | Permission |
|--------|------|------|------------|
| POST | /v1/auth/login | No | — |
| POST | /v1/auth/register | No | — |
| POST | /v1/auth/refresh | No | — |
| GET | /v1/auth/me | Yes | — |
| GET | /v1/auth/users | Yes | users:read |
| POST | /v1/auth/impersonate/{id} | Yes | users:impersonate |
| GET | /v1/cameras | Yes | cameras:read |
| POST | /v1/cameras | Yes | cameras:write |
| PUT | /v1/cameras/{id} | Yes | cameras:write |
| DELETE | /v1/cameras/{id} | Yes | cameras:delete |
| GET | /v1/cameras/scan/results | Yes | cameras:read |
| GET | /v1/chickens | Yes | chickens:read |
| GET | /v1/chickens/detected | Yes | chickens:read |
| GET | /v1/farms | Yes | farms:read |
| POST | /v1/farms | Yes | farms:write |
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
| Backend can't connect to DB | Ensure postgres container is healthy: `docker compose logs postgres` |
| Camera shows "Offline" | Check RTSP URL is correct, camera reachable from Docker host |
| HLS stream not loading | Verify Frigate is running: `curl http://localhost:5000/api/stats` |
| No detections appearing | Check Frigate MQTT connection: `docker compose logs frigate \| grep mqtt` |
| MQTT connection refused | Ensure mosquitto is running: `docker compose logs mosquitto` |
