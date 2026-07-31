# TVS Poultry Monitor — Localhost Development Guide

## Prerequisites

- **Docker Desktop** (Windows/Mac) or **Docker Engine** (Linux)
- **NVIDIA Container Toolkit** (optional — cv-engine will fall back to CPU, but it's slow)
- **Node.js 20+** (frontend dev without Docker)
- **Python 3.11+** (backend dev without Docker)

## Quick Start (Docker)

```bash
cp .env.example .env          # fill in secrets (see comments in the file)
docker compose up -d --build
```

Then:

| What | URL |
|------|-----|
| Frontend (nginx) | http://localhost:3001 |
| Backend API | http://localhost:18000 |
| API docs (Swagger) | http://localhost:18000/docs |
| cv-engine status | http://localhost:8700/status |
| go2rtc (video relay UI) | http://localhost:1984 |

Login with `admin@poultry.farm` / `DEFAULT_ADMIN_PASSWORD` (in `.env`).

> In prod overrides, ports on most services are closed — for local dev use the base `docker-compose.yml` only.

## Development Without Docker

### Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows  (Linux/Mac: source .venv/bin/activate)
pip install -e ".[dev]"

# The backend requires these env vars at startup (see .env.example):
#   DEFAULT_ADMIN_PASSWORD, POSTGRES_PASSWORD, JWT_SECRET, INFLUX_TOKEN, ENCRYPTION_KEY
#   Optional: ENCRYPTION_SALT (falls back to a built-in salt with a warning)
# Create backend/.env from the repo .env.example to satisfy them.

# Run the infra containers only (postgres, influxdb, redis, mosquitto)
docker compose up -d postgres influxdb redis mosquitto

# Point at the containerized Postgres (host port 5433) and start the API
$env:DATABASE_URL="postgresql+asyncpg://poultry:POSTGRES_PASSWORD@localhost:5433/poultry"
uvicorn app.main:app --reload --port 8000
# API now at http://localhost:8000  (VITE_API_URL default in .env.example is localhost:8000)
```

### cv-engine (optional, for real counts)

cv-engine must reach cameras over the host network, so it's easiest to run it in Docker:

```bash
docker compose up -d cv-engine go2rtc
```

Or run natively from `cv_engine/` after installing `requirements.txt` (needs FFmpeg + CUDA to be useful).

### Frontend

```bash
cd frontend
npm install
npm run dev                   # Vite dev server on http://localhost:3000
```

Vite proxies to the backend per `frontend/vite.config.ts`. Ensure `VITE_API_URL` points at your backend (default `http://localhost:8000`).

## Adding a Camera

1. Go to **Cameras** → **Add Camera**.
2. Enter the RTSP URL (e.g. `rtsp://user:pass@<nvr-ip>:554/cam/realmonitor?channel=0&subtype=0`) or register an NVR channel (`dvrip://user:pass@<nvr-ip>:34567?channel=0&subtype=0`).
3. cv-engine picks the camera up on its next sync (~10s) and starts a worker; go2rtc serves the HLS stream (`http://localhost:1984`) for on-demand viewing.
4. The camera appears on the Dashboard with live counts (click its card to expand the count).

## Key API Endpoints (`/v1/...`)

| Method | Path | Auth | Permission |
|--------|------|------|------------|
| POST | /auth/login | No | — |
| POST | /auth/register | No | — |
| POST | /auth/refresh | No (cookie) | — |
| POST | /auth/logout | Yes | — |
| GET | /auth/me | Yes | — |
| GET/PUT | /auth/users | Yes | users:read / users:write |
| POST | /auth/impersonate/{id} | Yes | users:impersonate |
| POST | /auth/deletion-request | Yes | — |
| GET | /auth/deletion-requests | Yes | users:write |
| POST | /auth/deletion-requests/{id}/approve\|reject | Yes | users:write |
| GET/POST/PUT/DELETE | /cameras | Yes | cameras:* |
| GET | /detection/live-counts | Yes | — |
| GET | /detection/history | Yes | — |
| GET | /detection/summary | Yes | — |
| GET/POST | /farms | Yes | farms:* |
| GET/POST/PUT/DELETE | /chickens, /coops, /alerts, /alerts/rules | Yes | per-module |
| GET/POST/PUT/DELETE | /media | Yes | media:* |
| POST | /nvr/connect, /nvr/discover, /nvr/register | Yes | nvr:* |
| POST | /xmeye/scan | Yes | — |
| GET | /health | No | — |
| WS | /ws?token=...&farm_id=... | Yes (query token) | — |

`/v1/internal/*` is for cv-engine ↔ backend communication and requires the `X-Internal-Token` header (`CV_ENGINE_API_KEY`).

## Testing

```bash
# Backend
cd backend
pytest -v                      # needs a Postgres (DATABASE_URL); many tests skip without one

# Frontend
cd frontend
npm run build                  # type-check (tsc -b) + vite build
npm run test                   # vitest (existing suites)
```

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Port conflict | Change the port in `docker-compose.yml` |
| Backend can't connect to DB | `docker compose logs postgres` |
| Camera shows offline | `docker compose logs cv-engine`; `curl http://localhost:8700/status` |
| Counts stay 0 | cv-engine CPU fallback is slow — confirm GPU (`nvidia-smi`) or check InfluxDB writes (`docker compose logs cv-engine`) |
| HLS video won't play | `curl http://localhost:1984/api/streams` to confirm the stream exists in go2rtc |
| Backend crashes at startup | It aborts if multi-worker env vars are set (`WORKERS`, `UVICORN_WORKERS` > 1) — single worker is required |
| Alembic migration fails with DuplicateColumn | DB was auto-created by `create_all`; run `alembic stamp 004` then `alembic upgrade head` |
