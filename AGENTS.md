persistent_summary:
  ## Goal
  Multi-farm, multi-user poultry monitoring system with a company-level super admin who manages all farms and users from a single dashboard, with impersonation for debugging.

  ## Constraints & Preferences
  - Exactly **one super admin** (`admin@poultry.farm`) -- no second super admin can be created, and the last one cannot be deleted.
  - Super admin has **full CRUD across all farms** (cameras, chickens, users, alerts, settings), can impersonate any user, can view all live feeds.
  - Only the super admin can impersonate; impersonation yields a 15-minute token scoped to the target user role/permissions/farm. A yellow banner shows "Viewing as {name} ({role})" with Stop button.
  - Each farm user (viewer/operator/admin) belongs to exactly one farm via farm_id FK on users.
  - All currency in Rs, deployment via Docker Compose + Tailscale (no Caddy, no Swarm).
  - Authorization Bearer header takes priority over httpOnly cookie so impersonation tokens can override the admin session cookie.

  ## Actual Architecture (as of last audit)
  - **CV pipeline**: Custom cv_engine/ service using YOLOv8 + OpenCV + FFmpeg. No Frigate, no HLS.
  - **go2rtc**: Used in production (docker-compose service, host network, read-only config mount) as an RTSP aggregator. cv-engine registers cameras via `PUT /api/streams?name=...&src=...`. Camera_worker consumes `rtsp://localhost:8554/{camera_id}`.
  - **Streaming**: Annotated JPEG frames via /cvws/{cam_id} WebSocket (cv-engine) + MJPEG fallback. No HLS.
  - **Media storage**: Local filesystem (/var/opt/poultry/media/farms/{farm_id}/). No MinIO/S3.
  - **MQTT**: Mosquitto is running but no code currently subscribes or publishes. Reserved for future use.
  - **Health/ReID**: No health classifier, no MCMT ReID, no FAISS. YOLOv8 detects only.
  - **Reverse proxy**: Nginx inside frontend container. No Caddyfile in active use.

  ## Progress
  ### Done
  - Impersonation backend: POST /auth/impersonate/{id} returns short-lived JWT. deps.py checks Authorization header before cookie. "users:impersonate" in super_admin permissions.
  - Impersonation frontend: AuthContext impersonating state (localStorage), axios bearer injection, ImpersonationBanner.tsx yellow banner, Settings.tsx "View as" button per user.
  - Single super admin enforcement: Register/delete endpoints enforce single super_admin. Frontend hides super_admin from role picker.
  - Full multi-farm backend: app/farms/ module, farm_id FK on 5 tables, get_farm_id() dependency, farm-scoped endpoints + InfluxDB queries + WebSocket channels.
  - Full multi-farm frontend: Farm switcher, admin/Farms.tsx, axios X-Farm-ID interceptor.
  - Farm_id scoping: 8/10 endpoints fixed (2 exempt - not in codebase).
  - Media module: backend/app/media/ local filesystem CRUD, farm-scoped paths, path traversal protection.
  - Alert rule evaluator (backend only): app/alerts/rules.py runs every 60s, 5 metric types, full deduplication.
  - NVR integration: app/nvr/ Dahua CGI + ONVIF WS-Discovery, multi-protocol RTSP URL builder.
  - CI/CD: GitHub Actions pytest + build gate, GHCR push, SSH deploy + health-check rollback.
  - Backup service: daily pg_dump + influx backup to local volume, 14-day retention.
  - Rate limiting: 20/min write endpoints, 10/min login.
  - Bug fixes (session 2026-07-28):
    - Removed duplicate cv-engine AlertEvaluator (wrong metric names, no dedup). Backend evaluator is sole owner.
    - ENCRYPTION_SALT made optional at startup -- now warns instead of crashing (security.py already had fallback).
    - /v1/internal/* endpoints protected by X-Internal-Token header validated against CV_ENGINE_API_KEY.
    - docker-compose.prod.yml hardened: Mosquitto port closed, DEBUG=false, ENVIRONMENT=production, CV_ENGINE_API_KEY wired.
    - PUT /auth/users/{id} now updates full_name (was missing from UserUpdate schema + router).
    - WebSocket /ws token extraction fixed: websocket.query_params.get("token") instead of broken FastAPI param binding.
    - Deleted stale backend/test.jpg stub file.
  - Hardcoded mortality demo (session 2026-08-01): frontend/src/demo/mortality.ts merges hardcoded "mortality" alerts + 2 photos (frontend/public/mortality/Mortality.jpg, Mortality2.jpg) into Alerts.tsx (red MORTALITY rows, local acknowledge for demo- ids) and MediaGallery.tsx (red "DEAD CHICKEN DETECTED" chip cards). Not backed by a real health/mortality model.
  - go2rtc + CI/CD restoration (session 2026-08-01):
    - Root cause of prod go2rtc 400/404 log errors: go2rtc config mounted read-only (`:ro`), so its `PUT /api/streams` API returns HTTP 400 `open /config/go2rtc.yaml: read-only file system` even though the stream registers in-memory and works. Re-registration on every ~10s camera sync duplicated calls. `ch5` in go2rtc.yaml has no DVR camera and yields 404s.
    - Rewrote cv_engine/camera_manager.py: `_is_go2rtc_source()`, `_register_go2rtc_stream()` returns bool and treats 400-with-"read-only" as success, dropped broken JSON POST fallback; new `CameraManager._go2rtc_target()` and `_ensure_go2rtc_streams()` with per-camera state + retry (re-register only on source change, prior failure with 30s backoff, or >GO2RTC_REGISTER_REFRESH_SECONDS stale). sync_cameras() calls it before start_camera().
    - cv_engine/config.py: added GO2RTC_REGISTER_REFRESH_SECONDS (default 300). .env.example documents it.
    - Fixed failing backend tests (blocked Deploy): tests/test_alerts_and_health.py::test_get_unacknowledged_count and tests/test_farm_scoping.py::test_alert_acknowledge_wrong_farm_returns_404 used stale Alert fields / omitted required farm_id. 69/69 pass locally.
    - Ruff: added [tool.ruff] config in backend/pyproject.toml (target-version py311; flake8-bugbear.extend-immutable-calls = [fastapi.Depends, app.auth.deps.require_permission] to clear 180 B008; ignore BLE001 + S110 as intentional defensive patterns), auto-fixed 202 violations (imports, unused imports, datetime UTC, PEP 604 unions), manually fixed 19 (SIM102 collapsible-if, F841 unused vars, PLW0602 stale `global`, DTZ003 utcnow, G201 logger.exception, TRY201 bare raise, RUF059, F402 loop-var shadowing). `ruff check .` passes. Added `ruff>=0.8.0` to dev extra so CI can run it.
    - Verified frontend: `npx tsc --noEmit` and `npm run build` both pass (Deploy gate).
    - Deploy pipeline (deploy.yml) = backend pytest + frontend npm run build (no ruff) -- now green locally. CI (ci.yml) = ruff check + pytest + tsc --noEmit -- now green locally.

  ### In Progress
  - (none)

  ### Blocked
  - (none)

  ## Key Decisions
  - Impersonation token flow: Backend generates token with target user sub/role/farm_id. Frontend stores in localStorage, injects via Authorization Bearer. Backend checks header before cookie.
  - Single super admin: Only admin@poultry.farm can be super_admin. Register endpoint blocks creation of another.
  - Farm-scoped data isolation: Every data endpoint uses get_farm_id() dependency. InfluxDB queries filter by farm_id tag.
  - WebSocket scoping: Backend WS connects client to farm_{id} channels. Frontend sends ?farm_id= in URL.
  - Camera streaming: cv-engine streams annotated JPEG via /cvws/{id} WebSocket to browser. Nginx proxies /cvws/* to cv-engine.
  - Internal auth: cv-engine uses X-Internal-Token: {CV_ENGINE_API_KEY} shared secret. Soft-gated -- if key not set, logs warning and allows (dev mode). Must be set in production.
  - Media storage: Local filesystem in Docker volume poultry_media. Farm-scoped path prefix. Path traversal blocked.
  - go2rtc: cv-engine registers cameras via `PUT /api/streams?name=..&src=..`; HTTP 400 with "read-only" body = success (in-memory) since config mount is read-only. Re-register only on source change / prior failure (30s backoff) / staleness (GO2RTC_REGISTER_REFRESH_SECONDS=300). No JSON POST fallback.
  - Ruff: `[tool.ruff.lint.flake8-bugbear].extend-immutable-calls` lists fastapi.Depends + app.auth.deps.require_permission (B008); BLE001/S110 ignored as intentional defensive logging.

  ## Next Steps
  1. Push the go2rtc + test + ruff fixes and verify Deploy/CI go green; confirm no more `go2rtc: 400/404` spam in prod logs.
  2. Add CV_ENGINE_API_KEY to .env (openssl rand -hex 32) and set it in prod.
  3. Write tests for media endpoints and farm_id scoping.
  4. Write frontend tests (Vitest + React Testing Library).
  5. Implement health scoring (cv-engine does not write to health measurement yet -- health endpoints return empty).

  ## Critical Context
  - farm_id is UUID FK on users (nullable -- null = super admin), cameras, chickens, alerts, alert_rules.
  - get_farm_id(): farm users -> JWT payload; super admin -> X-Farm-ID header or ?farm_id= param.
  - require_permission() checks permission string against role; farm scoping is a separate dependency.
  - Frontend localStorage.selected_farm_id drives X-Farm-ID axios header.
  - Impersonation: impersonation_token + impersonation_info in localStorage; cleared on 401/refresh.
  - hasPermission() checks impersonation permissions first, then real user role.
  - WebSocket token: ?token= query param OR access_token cookie. Read via websocket.query_params.get("token").
  - cv-engine processes cameras in subprocess per camera (multiprocessing). Single Uvicorn worker required on backend.
  - Alert evaluator: backend only (app/alerts/rules.py, every 60s). cv-engine evaluator REMOVED.
  - Internal API (/v1/internal/*): protected by X-Internal-Token header = CV_ENGINE_API_KEY.

  ## Relevant Files
  - backend/app/auth/router.py: All auth endpoints incl. impersonate, register/delete guards, update_user (now updates full_name).
  - backend/app/auth/deps.py: Token extraction (header > cookie), get_farm_id(), require_permission().
  - backend/app/auth/service.py: JWT helpers, Redis token blacklist, RBAC permission map, seed functions.
  - backend/app/auth/schemas.py: UserUpdate now includes full_name.
  - backend/app/api/v1/internal.py: /internal/* endpoints with _require_internal_token dependency.
  - backend/app/config.py: cv_engine_api_key setting, encryption_salt optional (warning not crash).
  - backend/app/cameras/router.py: Camera CRUD, ONVIF scan, assign-coop; all farm-scoped.
  - backend/app/detection/router.py: Detection stats/history/summary per-camera + global; farm-scoped.
  - backend/app/health/router.py: Health scores + summary from InfluxDB; farm-scoped.
  - backend/app/alerts/rules.py: AlertRuleEvaluator -- sole alert evaluator, 60s interval.
  - backend/app/alerts/router.py: Alert CRUD, acknowledge, alert rules CRUD.
  - backend/app/media/client.py: Local filesystem media CRUD with farm-scoped paths.
  - backend/app/media/router.py: Media upload/download/list/delete with path traversal protection.
  - backend/app/nvr/router.py: NVR connect/discover/register, multi-protocol RTSP URL builder.
  - backend/app/websocket/router.py: /ws WebSocket -- token from query_params (fixed), farm-scoped channels.
  - frontend/src/auth/AuthContext.tsx: Auth state, impersonation, farm selection, hasPermission().
  - frontend/src/api/axios.ts: Axios instance with X-Farm-ID + impersonation interceptors + 401 refresh.
  - frontend/src/components/ImpersonationBanner.tsx: Yellow banner with Stop button.
  - frontend/src/layout/ResponsiveShell.tsx: Route definitions, offline banner, impersonation banner.
  - cv_engine/server.py: cv-engine FastAPI -- camera sync loop (X-Internal-Token), WS frame streaming, MJPEG.
  - cv_engine/camera_manager.py: Per-camera subprocess manager + go2rtc stream registration (`_ensure_go2rtc_streams`, `_go2rtc_target`, 400-as-success).
  - cv_engine/camera_worker.py: Per-camera subprocess -- FFmpeg + YOLOv8 + frame_store + detection_queue.
  - cv_engine/stream_manager.py: RtspCameraStream -- FFmpeg subprocess, JPEG frame extraction.
  - cv_engine/influx_writer.py: InfluxWriter thread -- drains detection_queue to InfluxDB.
  - cv_engine/config.py: CV engine settings incl. CV_ENGINE_API_KEY, GO2RTC_REGISTER_REFRESH_SECONDS.
  - backend/pyproject.toml: [tool.ruff] config (py311, B008 extend-immutable-calls, BLE001/S110 ignore); dev extra includes ruff>=0.8.0.
  - docker-compose.yml: All services. cv-engine and backend now receive CV_ENGINE_API_KEY.
  - docker-compose.prod.yml: Prod overrides -- ports closed, DEBUG=false, API key wired.
  - .env.example: CV_ENGINE_API_KEY documented.
  - Dockerfile: Multi-stage -- frontend (nginx) + backend (uvicorn). cv-engine has its own dockerfile.
  - .github/workflows/deploy.yml: CI test + build + SSH deploy with rollback (no ruff step).
  - .github/workflows/ci.yml: ruff check + pytest + frontend tsc --noEmit.
persistent_summary_offset: 0
