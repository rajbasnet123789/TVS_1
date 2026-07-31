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
  - **CV pipeline**: Custom cv_engine/ service using YOLOv8 + OpenCV + FFmpeg. No Frigate, no HLS, no go2rtc.
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

  ## Next Steps
  1. Add CV_ENGINE_API_KEY to .env (openssl rand -hex 32) and set it in prod.
  2. Write tests for media endpoints and farm_id scoping.
  3. Write frontend tests (Vitest + React Testing Library).
  4. Implement health scoring (cv-engine does not write to health measurement yet -- health endpoints return empty).

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
  - cv_engine/camera_manager.py: Manages subprocess per camera.
  - cv_engine/camera_worker.py: Per-camera subprocess -- FFmpeg + YOLOv8 + frame_store + detection_queue.
  - cv_engine/stream_manager.py: RtspCameraStream -- FFmpeg subprocess, JPEG frame extraction.
  - cv_engine/influx_writer.py: InfluxWriter thread -- drains detection_queue to InfluxDB.
  - cv_engine/config.py: CV engine settings incl. CV_ENGINE_API_KEY.
  - docker-compose.yml: All services. cv-engine and backend now receive CV_ENGINE_API_KEY.
  - docker-compose.prod.yml: Prod overrides -- ports closed, DEBUG=false, API key wired.
  - .env.example: CV_ENGINE_API_KEY documented.
  - Dockerfile: Multi-stage -- frontend (nginx) + backend (uvicorn). cv-engine has its own dockerfile.
  - .github/workflows/deploy.yml: CI test + build + SSH deploy with rollback.
persistent_summary_offset: 0
