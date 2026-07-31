# TVS Poultry Monitor — Architecture

> **Product:** Multi-farm, multi-user poultry monitoring  
> **Status:** Count-only detection (no per-chicken identity), count-first dashboard with a go2rtc HLS relay for on-demand viewing

## 1. System Overview

The system monitors chicken counts across one or more farms using IP cameras / an NVR:

- **Detects** every chicken in a camera frame with a YOLOv8 model and counts them
- **Stores** per-camera, per-farm detection counts in InfluxDB (time-series)
- **Alerts** farm staff when configured rules fire (e.g. headcount drop, camera offline)
- **Relays** NVR camera video through go2rtc (HLS at `:1984`, host network) — available for ad-hoc viewing; the dashboard is count-first
- **Manages** multiple farms from a single company dashboard (super admin)
- **Isolates** all data by `farm_id`; farm users belong to exactly one farm

What it deliberately does **not** do today:

- No per-chicken identity/re-identification (no MCMT, no FAISS, no ReID models)
- No health classification (the `health` measurement is currently unpopulated)
- No video playback inside the SPA (count cards only; go2rtc HLS is reachable directly)
- No continuous video recording or annotation overlays
- No MQTT consumers (Mosquitto is deployed but unused — reserved)

## 2. End-to-End Data Flow

```
 IP Camera / NVR
   │  RTSP (tcp)            ┌──────────────────────────────────────────┐
   ▼                        │  go2rtc  (host network)                  │
 ┌──────────┐   ┌────────┐  │  · RTSP relay  :8554                     │
 │ go2rtc   │──▶│ cv-engine│  │  · HLS API     :1984                    │
 │ :8554/   │   │ :8700   │  └──────────────────────────────────────────┘
 │ ch0..15  │   │ (GPU)   │
 └──────────┘   │  │
                │  │  FFmpeg pulls RTSP per camera (subprocess)
                │  ▼
                │  YOLOv8 counts chickens per frame
                │  ▼
                │  detection events → queue
                │  ▼
                │  InfluxWriter → InfluxDB (bucket=detections, farm_id tag)
                └───────────────┬────────────────────────────────────────
                                │
 ┌──────────────┐   REST / WS   ▼   ┌───────────────────────┐
 │  Frontend    │◀─────────────│────│  Backend (FastAPI)    │
 │  nginx :80   │──────────────│───▶│  · reads counts from  │
 │  · SPA       │   /api, /ws  │    │    InfluxDB           │
 └──────┬───────┘              │    │  · farm-scoped REST   │
        │                      │    │  · WebSocket channels │
        │                      │    │  · alert evaluator    │
        │                      │    │  · auth/impersonation │
        │                      │    └───────────┬───────────┘
        │                      │                │
        │ (video: go2rtc HLS   │        ┌───────┴────────┐
        │  at http://<host>:1984│       │ PostgreSQL     │
        │  is reachable        │        │ Redis          │
        │  directly, not yet   │        └────────────────┘
        │  embedded in SPA)    │
        ▼
   browser renders count cards
```

Key decisions that shape this flow:

- **cv-engine runs on the host network** so it can reach Tailscale-routed camera subnets (Docker bridge NAT would block them). It talks to the backend via `http://localhost:18000`.
- **go2rtc also runs on the host network** and ingests the NVR channels directly (`rtsp://192.168.31.169:554/cam/realmonitor?channel=N&subtype=0` with a DVRIP fallback).
- **Backend runs exactly one Uvicorn worker** (`assert_single_worker()` in `app/main.py`); it hosts process-local state (camera sync, scan tasks). The 0bfdf23 "4 workers" experiment was reverted for this reason.
- **Counts are pulled by the frontend** from `GET /detection/live-counts` on a shared 3-second poll (a global singleton in `useLiveCounts.ts` — one poll loop for all consumers, not one per card).

## 3. Component Layers

### 3.1 Camera / NVR Layer

- Cameras connect to a **Dahua/TVS NVR** on the LAN (e.g. `192.168.31.169`, RTSP `:554`, DVRIP `:34567`).
- The backend has an **NVR module** (`app/nvr/`) with Dahua CGI + ONVIF WS-Discovery, plus an **XMEye** LAN scanner (`app/xmeye/`, proxied to cv-engine which broadcasts on the host network).
- Camera records in PostgreSQL store RTSP/DVRIP URLs; cv-engine registers/refreshes corresponding streams in go2rtc.

### 3.2 go2rtc (Video Relay)

- Static streams `ch0..ch15` defined in `go2rtc/go2rtc.yaml`, mirroring NVR channels.
- Each stream has an FFmpeg RTSP-TCP producer as primary and a `dvrip://` producer as fallback (protocol failover).
- Exposes the HLS API on `:1984` (`/api/hls/{stream}.m3u8`) and an RTSP relay on `:8554`.
- Run on the host network and not exposed through the public reverse proxy (nginx). The HLS feed is reachable directly at `http://<host>:1984` for ad-hoc viewing; the SPA does **not** embed it yet (count cards only).

### 3.3 cv-engine (Detection Pipeline)

A separate FastAPI service (`cv_engine/`, NVIDIA CUDA image, host network):

- **Camera manager** (`camera_manager.py`) launches **one subprocess per camera** (multiprocessing) and syncs camera config from the backend every ~10s (`GET /v1/internal/cameras`, authenticated with `X-Internal-Token: {CV_ENGINE_API_KEY}`).
- **Stream manager** (`stream_manager.py`) runs one FFmpeg subprocess per camera that pulls RTSP and extracts JPEG frames into an in-memory `frame_store` (latest raw frame per camera).
- **Camera worker** (`camera_worker.py`) reads the latest raw frame, runs YOLOv8 via `object_tracker.py` (CUDA + FP16, per-camera `track_id`), applies the optional ROI polygon, and pushes detection events (box + confidence + track_id) onto a multiprocessing `detection_queue`.
- **Influx writer** (`influx_writer.py`) drains the queue in batches and writes `detections` points tagged `camera_id`/`farm_id`/`track_id`/`class_name`, with `confidence` + box fields.
- **Status reporting** (`PATCH /v1/internal/cameras/status`) keeps `cameras.status` accurate in PostgreSQL.
- Endpoints: `/health`, `/status`, `/xmeye-scan`. (WebSocket/JPEG streaming was removed in the count-only migration.)

### 3.4 Backend API Layer (FastAPI)

Single worker, lifespan startup: `assert_single_worker()` → `init_db()` (creates tables if missing) → seeds roles/default farm/super admin → starts the alert evaluator → optional Sentry/NVR init.

Modules (all mounted under `/v1`): `auth`, `farms`, `cameras`, `chickens`, `coops`, `detection`, `alerts`, `analytics`, `environment`, `health`, `media`, `nvr`, `xmeye`, `internal`, plus the WebSocket router at `/ws`.

- **Farm scoping** — every data endpoint resolves a `farm_id` (JWT for farm users, `X-Farm-ID` header/`?farm_id=` for the super admin) and filters queries by it.
- **Internal API** (`/v1/internal/*`) — used by cv-engine, protected by the shared `CV_ENGINE_API_KEY`.
- **Rate limiting** — write endpoints 20/min, login 10/min (slowapi).
- **Alert evaluator** — `app/alerts/rules.py` runs every 60s, evaluates 5 metric types with full deduplication.

### 3.5 Frontend Dashboard (React)

Single-page app (Vite + MUI, Outfit font, teal/green theme). Served by nginx, which also reverse-proxies `/api/` and `/ws` to the backend.

Routes (protected unless noted):

| Route | Page |
|-------|------|
| `/` | Dashboard (counts + camera grid) |
| `/coop-map` | Coop map |
| `/live` | Live feed |
| `/analytics` | Analytics |
| `/alerts` | Alerts |
| `/reports` | Reports |
| `/profit-loss` | Profit & loss |
| `/media` | Media gallery |
| `/settings` | Settings (incl. Delete Account & Data, Deletion Requests admin panel) |
| `/admin/farms` | Farm management (super admin) |
| `/privacy-policy` | Privacy policy (**public**, no auth) |

State/behaviour highlights:

- **`useCameras`** — shared global camera state (one fetch, cached, shared by all pages).
- **`useLiveCounts`** — global singleton poll loop (one 3s interval for the whole app).
- **Auth context** — access token in localStorage, refresh via httpOnly cookie; impersonation token overrides via `Authorization: Bearer`.
- **Farm switcher** — drives the `X-Farm-ID` axios header (super admin only).

### 3.6 Data Storage Layer

| Store | Usage |
|-------|-------|
| **PostgreSQL** | Users, farms, cameras, chickens, coops, alerts, alert rules, media metadata, deletion requests. Migrated via Alembic (`001_mcmt` → `005`). Schema also auto-created at startup (`create_all`) — see [deployment.md](deployment.md) for the stamp/upgrade note. |
| **InfluxDB** | Time-series detection data (bucket `detections`, tagged with `farm_id`/`camera_id`). Source of truth for counts/history/summary. |
| **Redis** | Token blacklist, impersonation short-term state. |
| **Local filesystem** | Media files at `/var/opt/poultry/media/farms/{farm_id}/` (volume `poultry_media`). Farm-scoped paths, path-traversal protected. |

## 4. Multi-Farm Model & Auth

- **Users** carry an optional `farm_id` FK (`NULL` = super admin). Roles: `viewer`, `operator`, `admin`, `super_admin`.
- **Super admin** (`admin@poultry.farm`) is exactly one — registration of a second is blocked and the last one cannot be deleted. It can CRUD across all farms and view any live feed via the farm switcher.
- **Impersonation** — `POST /auth/impersonate/{id}` mints a 15-minute JWT scoped to the target user's role/farm. The frontend stores it in `localStorage` and sends it as `Authorization: Bearer`; the backend checks the header **before** the httpOnly cookie so the impersonation token wins. A yellow banner shows "Viewing as {name} ({role})" with a Stop button.
- **Account deletion requests** — `POST /auth/deletion-request` deactivates the account (sets `is_active=False`, blacklists tokens) and creates a pending `DeletionRequest`. Admins approve (permanent delete) or reject (reactivate) via Settings → Deletion Requests.

## 5. Alert System

`app/alerts/rules.py` (backend-only, 60s interval) evaluates user-configurable rules. Supported metric types include inactivity, headcount drop, missing-chicken, and camera-related conditions. Each rule is farm-scoped; results are deduplicated so the same condition does not spam the same alert. Alerts are stored in PostgreSQL and surfaced through the API + WebSocket channel for the farm.

> The previous cv-engine-side evaluator was removed — the backend evaluator is the sole owner.

## 6. API Surface (summary)

- `POST /v1/auth/login|register|refresh|logout`, `GET /v1/auth/me`, `GET/PUT /v1/auth/users`, `POST /v1/auth/impersonate/{id}`, `POST/GET /v1/auth/deletion-request(s)`, `POST .../deletion-requests/{id}/approve|reject`
- `GET/POST/PUT/DELETE /v1/cameras`, ONVIF scan + assign-coop, `/v1/cameras/fix-channels`
- `GET /v1/detection/live-counts`, `history`, `summary`, per-camera + global
- `/v1/alerts`, `/v1/alerts/rules`, `/v1/chickens`, `/v1/coops`, `/v1/farms`, `/v1/health`, `/v1/analytics`, `/v1/environment`, `/v1/media`, `/v1/nvr/*`, `/v1/xmeye/*`
- `/v1/internal/*` (cv-engine ↔ backend, `X-Internal-Token`)
- `WS /ws?token=...&farm_id=...`
- `GET /health`

OpenAPI docs at `/docs` on the backend.

## 7. Deployment Architecture

Docker Compose; no Swarm, no Caddy. The frontend nginx container is the only public entry point and reverse-proxies `/api/` + `/ws`. Production overrides (`docker-compose.prod.yml`) close host ports on every service except the frontend (`127.0.0.1:3001:80`).

- **Networking:** cv-engine and go2rtc use `network_mode: host` (Tailscale routes, LAN camera reach). Backend reaches cv-engine via `host.docker.internal:8700`.
- **Remote access:** Tailscale on the host; the frontend nginx serves plain HTTP on `127.0.0.1:3001` and **Tailscale Serve terminates HTTPS** for the public domain (`DOMAIN`). No Caddy/Swarm.
- **Updates:** `git pull` on the server + rebuild affected containers (see [deployment.md](deployment.md)). CI also builds/pushes GHCR images and SSH-deploys with health-check rollback.
- **Backups:** `backup` service — daily `pg_dump` + `influx backup` to the `poultry_backups` volume, 14-day retention.

## 8. Security

- JWT access tokens (15 min) + rotating refresh cookie (7 days) with theft detection; `Authorization: Bearer` wins over cookie.
- Single super admin enforcement; farm-scoped data isolation on every endpoint.
- `CV_ENGINE_API_KEY` shared secret guards `/v1/internal/*` (warning-only in dev when unset).
- Rate limiting (write 20/min, login 10/min).
- nginx security headers + CSP; `frame-ancestors 'none'`; XSS/nosniff headers.
- Media path-traversal protection; farm-scoped media paths.
- Production env hardening (`DEBUG=false`, `COOKIES_SECURE=true`, Mosquitto port closed).

## 9. Observability & Ops

- Backend logs carry a per-request `X-Request-ID`.
- Optional Sentry (`SENTRY_DSN`).
- Docker healthchecks on postgres, influxdb, redis, backend, cv-engine.
- `cv-engine /status` reports per-camera worker state; camera `online/offline` is synced back to PostgreSQL.

## 10. Known Gaps / Roadmap

- `health` endpoints return empty until a health classifier writes to InfluxDB.
- No per-chicken identity (counting only).
- Mosquitto is deployed but nothing publishes/subscribes yet.
- Frontend test coverage (Vitest + RTL) is not yet wired into CI.
- Media endpoint + farm-scoping tests partially exist (backend suite is not yet green without a local DB).

See [TODOS.md](TODOS.md) for the tracked work.
