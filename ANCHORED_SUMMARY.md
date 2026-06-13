## Goal
Build and deploy Phase 1 (Foundation) of the poultry monitoring system — backend API, frontend dashboard, camera management with ONVIF discovery, live video via MediaMTX, full RBAC auth — on localhost.

## Constraints & Preferences
- All Phase 1 code goes **outside** `AI_MODEL/` (model training is a separate project)
- Localhost-only development; no production deployment yet
- Media server: **MediaMTX** (RTSP → HLS for browser playback via HLS.js)
- Authentication: **Full RBAC** with 4 roles (viewer, operator, admin, super_admin)
- Camera onboarding: **ONVIF discovery** (WS-Discovery multicast) + manual RTSP URL entry
- GPU/NVIDIA Container Toolkit available but not configured yet — CPU-only for now
- **Mock cameras** needed to test the pipeline without real RTSP streams
- No existing services on ports 3000, 8000, 5432, 6379, 8086, 8888, 8554, 9000, 9001, 9997

## Progress
### Done
- Created full Phase 1 project structure at `A:\TVS_1\` (67+ files across backend, frontend, root configs, docs)
- **Root configs**: docker-compose.yml (8 services: postgres, influxdb, redis, minio, mediamtx, backend, frontend, mock-stream), mediamtx.yml (flat config for v1.19.0, now with `authMethod: internal` + `authInternalUsers` for api/monitoring + static paths for `testcam`/`webcam`), .env.example, README.md, .gitignore (Python/Node/Docker/IDE/OS/logs)
- **Backend** (FastAPI + async SQLAlchemy, 20+ files):
  - Auth module: JWT access/refresh tokens, bcrypt (<4.1), RBAC with 4 roles, permission-gated DI
  - Cameras module: CRUD, RTSP grabber (OpenCV), ONVIF discovery (raw WS-Discovery sockets), mock camera generator (`mock://` prefix concept), MediaMTX API integration with HTTP Basic Auth using v3 endpoints
  - Chickens module: CRUD with `chicken_id` (0–49)
  - WebSocket manager: channel-based pub/sub (`camera_status`, `detections`, `alerts`)
  - Pydantic Settings from env, Alembic, lifespan events, CORS
- **Frontend** (React + Vite + TypeScript + MUI v6, 20 files):
  - Pages: Dashboard (renders stats + empty state), LiveFeed, Cameras (Scan Network + Add Camera buttons), Chickens (read-only table), Settings (profile, password, user mgmt placeholder)
  - Components: CameraFeed (HLS.js with reconnect), CameraGrid (responsive via legacy Grid), StatCard, ONVIFScanModal (progress table → Add)
  - Hooks: useWebSocket (exponential backoff), useCameras (CRUD + scan + poll)
  - Auth: AuthContext (token refresh interceptor), Login (pre-filled admin@poultry.farm / admin123), ProtectedRoute (permission-gated redirect)
  - Layout: Sidebar (responsive drawer, permission-filtered nav), Header (user menu, theme toggle), ResponsiveShell
- **Docs**: localhost-development-guide.md
- **All 8 containers running and healthy** (postgres, influxdb, redis, minio, mediamtx, backend, frontend, mock-stream)
- **Login flow verified** via frontend: login page → Sign In → Dashboard with sidebar
- **API endpoints verified**: `GET /health`, `POST /v1/auth/login`, `GET /v1/auth/me`, `GET /v1/cameras`, `GET /v1/chickens`
- **MediaMTX v3 API endpoints working**: `POST /v3/config/paths/add/*name` (add path), `DELETE /v3/config/paths/delete/*name` (delete path), `GET /v3/config/paths/list/get` (inspect), `GET /v3/paths/list/get` (active paths), `GET /v3/hlsmuxers/list/get` (HLS muxers)
- **Full HLS video pipeline verified end-to-end**:
  - `MockCameraGenerator` → synthetic chicken detection frames (640x480, 4 chickens with wandering bboxes)
  - `mock_stream.py` → pipes frames through ffmpeg (H264, libx264 ultrafast) as RTSP to MediaMTX
  - MediaMTX v1.19 → receives RTSP, produces LL-HLS segments (2s segments, 266ms parts)
  - HLS served at `http://localhost:8888/{path_name}/index.m3u8` (root-level, no `/hls/` prefix)
  - Verified: multivariant playlist, media playlist with segments, 181KB MP4 segments downloadable at HTTP 200
- **`MockCameraGenerator` fully wired**: `backend/mock_stream.py` script uses `MockCameraGenerator.generate_frame()` → `asyncio.subprocess` ffmpeg pipe → RTSP → MediaMTX
- **Fixed .gitignore**: `backend/.gitignore` → root-level `.gitignore` covering all stacks
- **Fixed backend Dockerfile**: `libgl1-mesa-glx` → `libgl1` for Debian Trixie
- **Fixed frontend Dockerfile**: removed `package-lock.json` copy
- **Fixed MUI Grid v6**: legacy `Grid` with `item` + `xs`/`sm`/`md` across 3 files
- **Fixed MediaMTX flat config**: v1.19.0 requires flat keys, not nested objects
- **Fixed MediaMTX API auth**: added `authMethod: internal` + `authInternalUsers` with `admin`/`admin123` granting `api` + `metrics` + `pprof`
- **Fixed bcrypt**: pinned `<4.1.0` for passlib compatibility
- **Fixed user role lazy load**: added `selectinload(User.role)` in auth deps to avoid async session closing
- **Fixed `NameError: name 'db' is not defined`**: passed `db` parameter to `_delete_mediamtx_stream`
- **Fixed MediaMTX API endpoint**: changed from `/v2/paths/add` to `/v3/config/paths/add/*name` (v2 removed in v1.19)
- **Fixed HLS URL format**: MediaMTX v1.19 mounts HLS at root (`/{path}/index.m3u8`), not `/hls/{path}/index.m3u8`

### In Progress
- Testing frontend Cameras page with real camera data (1 working camera)
- Next: test WebSocket, RBAC enforcement, change password flow

### Blocked
- Real camera/ONVIF scan testing deferred until Docker-bridge multicast solution or Linux/WSL2 host networking is available
- MockCameraGenerator generates synthetic frames but does not simulate detection AI output yet (Phase 2)

## Key Decisions
- **MediaMTX v1.19 HLS URL**: Served at root level (`GET /{path_name}/index.m3u8`), NOT under `/hls/` prefix. Backend generates `/{path_name}/index.m3u8` and frontend uses `VITE_MEDIAMTX_HLS_BASE=http://localhost:8888` to construct full URLs
- **MediaMTX v1.19 path management**: Use `/v3/config/paths/add/*name` for creation and `/v3/config/paths/delete/*name` for removal. The v2 API (`/v2/paths/add`) was removed in v1.19. Config paths are persistent across restarts (saved to config); active paths are runtime-only
- **HLS muxers created on-demand**: Muxers are created when a viewer first requests the HLS playlist. No HLS muxer exists until first access. LL-HLS mode with cookie-based session management
- **MediaMTX requires path config before accepting publishers**: Publishers can only push to paths that are explicitly configured (statically in mediamtx.yml or via API). No implicit path creation for publishers
- **MockCameraGenerator + ffmpeg pipeline**: Python script uses `asyncio.create_subprocess_exec` to pipe raw BGR24 frames to ffmpeg, which encodes to H264 and pushes RTSP to MediaMTX. Works as a standalone docker-compose service (`mock-stream`) using the backend image
- **MediaMTX API requires explicit auth config**: v1.19 defaults to localhost-only API access. Added `authInternalUsers` with `admin`/`admin123` granting `api` permission
- **Backend uses HTTP Basic Auth for MediaMTX API**: `mediamtx_api_user`/`mediamtx_api_pass` settings passed via docker-compose env vars
- **No external `ws-discovery` library**: PyPI package doesn't exist; ONVIF scan uses raw UDP sockets directly
- **Bridge networking with `host.docker.internal`**: ONVIF multicast won't work on Docker Desktop; revert to host networking on Linux/WSL2 if multicast is needed
- **Two-stage AI pipeline deferred to Phase 2**: Phase 1 is pure infrastructure
- **Default super-admin**: `admin@poultry.farm` / `admin123` seeded on first startup
- **Token storage**: localStorage with Axios interceptor; httpOnly cookies for production later

## Next Steps
1. Test frontend Cameras page shows the working test camera
2. Test WebSocket connection and message flow
3. Test RBAC enforcement (403 for missing permissions)
4. Test change password flow
5. Test ONVIF scan (when multicast-capable environment available)
6. Wire real cameras for end-to-end validation
7. Phase 2: AI inference pipeline (Celery, YOLO, ByteTrack, re-ID)

## Critical Context
- **API prefix structure**: `app.include_router(api_v1_router)` → router has `prefix="/v1"` → full login path: `/v1/auth/login` (not `/api/v1/auth/login`)
- **HLS URL format**: `GET /{path_name}/index.m3u8` on port 8888 (MediaMTX v1.19 root-level HLS). NOT `/hls/{path_name}/index.m3u8`
- **Backend must be rebuilt** after any Python code change. Either `docker compose build backend && docker compose up -d backend` or use `docker compose watch`
- **Mock stream**: `docker compose up -d mock-stream` starts a synthetic chicken camera sending RTSP to MediaMTX at path `testcam`. HLS available at `http://localhost:8888/testcam/index.m3u8`
- **PostgreSQL port 5432** may conflict with local postgres; stop local instance or change mapped port
- **InfluxDB init** requires 3 matching env vars for recreation
- **Default login seeded** only when roles table is empty; to reset: `docker compose down -v && docker compose up -d`
- **ONVIF multicast** requires host networking (not available on Docker Desktop)
- **`.gitignore`** at `A:\TVS_1\.gitignore` covering `__pycache__/`, `node_modules/`, `.venv/`, `.env`, IDE files, `.DS_Store`, `*.log`

## Relevant Files
- **Root**: `docker-compose.yml` — 8-service bridge networking with mock-stream; `mediamtx.yml` — flat v1.19 with `authMethod: internal`, `authInternalUsers`, static paths `testcam`/`webcam`; `.gitignore` at project root
- **Backend**: `app/config.py` — `mediamtx_api_user`/`mediamtx_api_pass` settings; `app/cameras/service.py` — `_create_mediamtx_stream` uses v3 API, `_delete_mediamtx_stream` takes `db` param; `app/auth/deps.py` — `selectinload(User.role)` fix; `mock_stream.py` — standalone RTSP publisher using `MockCameraGenerator`
- **Frontend**: `src/components/CameraFeed.tsx` — HLS.js with `VITE_MEDIAMTX_HLS_BASE` (root-level, no `/hls/` prefix); `src/auth/AuthContext.tsx` — token management
- **MediaMTX**: `POST /v3/config/paths/add/{name}` — add path; `DELETE /v3/config/paths/delete/{name}` — delete path; `GET /v3/paths/list` — list active paths; `GET /v3/hlsmuxers/list/get` — HLS muxer status
