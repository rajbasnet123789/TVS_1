persistent_summary:
  ## Goal
  Multi-farm, multi-user poultry monitoring system with a company-level super admin who manages all farms and users from a single dashboard, with impersonation for debugging.

  ## Constraints & Preferences
  - Exactly **one super admin** (`admin@poultry.farm`) — no second super admin can be created, and the last one cannot be deleted.
  - Super admin has **full CRUD across all farms** (cameras, chickens, users, alerts, settings), can impersonate any user, can view all live feeds.
  - Only the super admin can impersonate; impersonation yields a 15-minute token scoped to the target user's role/permissions/farm. A yellow banner shows "Viewing as {name} ({role})" with Stop button.
  - Each farm user (viewer/operator/admin) belongs to exactly one farm via `farm_id` FK on `users`.
  - All currency in ₹, deployment via Docker + Tailscale.
  - Authorization Bearer header takes priority over httpOnly cookie so impersonation tokens can override the admin's session cookie.

  ## Progress
  ### Done
  - **Impersonation backend**: `POST /auth/impersonate/{id}` returns a short-lived JWT scoped to the target user's role/permissions/farm. `deps.py` now checks Authorization header before cookie. `"users:impersonate"` added to super_admin permission map.
  - **Impersonation frontend**: `AuthContext` — `impersonating` state (persisted via localStorage), `startImpersonating()`, `stopImpersonating()`. Axios interceptor adds `Authorization: Bearer <impersonation_token>` when set. `ImpersonationBanner.tsx` — yellow banner with Stop button. `Settings.tsx` — "View as" button per user row. `ResponsiveShell.tsx` — banner rendered above page content.
  - **Single super admin enforcement**: Register endpoint rejects creating a second super_admin. Delete endpoint rejects deleting the last one. Frontend hides `super_admin` from role helper text and hides Delete button for super_admin rows.
   - **Architecture doc updated** to v3.0 — multi-farm overview, impersonation, farm-scoped RBAC table, new API endpoints (farms CRUD + impersonate), updated DB diagram with `farms` table + `farm_id` FKs, security section with farm-level data isolation.
   - **Full Frigate VMS integration** (Phases 1–9): Frigate handles all RTSP ingestion, motion-triggered bird detection, recording, and HLS streaming via go2rtc. Custom health classifier (best.pt, 32 classes) runs on Frigate snapshots via MQTT subscriber. MCMT ReID tracker (MiewID + FAISS) as shared singleton, fed by subscriber. Alembic migration removes legacy `CameraStream` table. NVR router for auto-discovery of ONVIF cameras. Frontend CameraFeed uses `hls.js` targeting `/api/frigate/hls/` via nginx proxy. All docs updated, .env.example refreshed, stale references cleaned up.
   - **Architecture doc updated** to v4.0 — sections 3, 10, 11, 16, 18, 22, 23 updated for Frigate pipeline, latency budget, metrics, runbook, capacity planning.
  - **Full multi-farm backend (pre-session)**: 25+ files — `app/farms/` module, `farm_id` FK on 5 tables, Alembic migration, `get_farm_id()` dependency, per-endpoint filtering, farm-scoped WebSocket channels, worker writes `farm_id` tag to InfluxDB.
  - **Full multi-farm frontend (pre-session)**: Farm switcher dropdown, `admin/Farms.tsx` page, `AuthContext` farm list + selection, axios `X-Farm-ID` interceptor.
  - **End-to-end audit completed** — found 10 backend endpoints missing farm_id scoping + 3 frontend issues.
  - **Farm_id scoping fixed on 8/10 backend endpoints**:
    - `GET /chickens/detected` → added `farm_id` param to `query_detected_chickens()` with InfluxDB filter.
    - `GET /health/scores` → added `farm_id` param to `query_health_scores()` with InfluxDB filter.
    - `GET /cameras/{id}/detection/stats` → Camera ownership check (404 if not found, 403 if wrong farm).
    - `GET /cameras/{id}/detection/history` → Camera ownership check.
    - `GET /cameras/{id}/detection/summary` → Camera ownership check.
    - `PUT /alerts/{id}/acknowledge` → Alert ownership check.
    - `PUT /alerts/rules/{id}` → AlertRule ownership check.
    - `DELETE /users/{id}` → farm_id check on target (super admins can delete any user; farm admins can only delete users in their farm).
  - **Frontend WebSocket**: `useWebSocket.ts` now appends `?farm_id=` query param from localStorage.
  - **Axios interceptor**: token refresh now updates `impersonation_token` in localStorage.
  - **Analytics.tsx**: removed duplicate `api.get('/detection/global/history')` call.
  - **MinIO media integration**: New `backend/app/media/` module with MinIO client, upload/download/delete/list endpoints, and farm-scoped path isolation (`farms/{farm_id}/` prefix). Initialized in `main.py` lifespan.
  - **Production readiness (Phase 1 — Security)**: MQTT auth (`password_file`, credentials in subscriber + Frigate config), HLS stream auth (nginx `auth_request` + `/auth/validate-token` endpoint), HTTPS via Caddy auto-TLS, dev backdoor removed (`admin/admin` fallback + config flags deleted), MinIO TLS wired via `MINIO_SECURE` env var.
  - **Production readiness (Phase 2 — Data & O11y)**: Automated backup service (`scripts/backup.sh` + `Dockerfile.backup` — daily pg_dump + influx backup to MinIO, 14-day retention), Sentry error monitoring gated by `SENTRY_DSN`.
  - **Production readiness (Phase 3 — Quality)**: CI test job (pytest + frontend build before deploy), CORS whitespace fix (strip()), model SHA-256 integrity verification on load, rate limiting on 22 write endpoints (20/min) across 9 routers.
  - **Deployment guide updated**: `.env` table with all vars, MQTT password file step, firewall table with Caddy ports, TLS section simplified (Caddy built-in), post-deploy verification steps, CI/CD pipeline docs, full security checklist.

  ### In Progress
  - (none)

  ### Blocked
  - (none)

  ## Key Decisions
  - **Impersonation token flow**: Backend generates a token with the target user's `sub`, `role`, and `farm_id`. Frontend stores it in `localStorage` and injects it via `Authorization: Bearer` header. Backend checks Authorization header before cookie, so the impersonation token overrides the admin's cookie. Stop impersonating clears the token and reloads.
  - **Single super admin**: Only `admin@poultry.farm` can have `super_admin` role. Register endpoint blocks creation of another. Frontend hides `super_admin` from role picker.
  - **Farm-scoped data isolation**: Every data endpoint uses `get_farm_id()` dependency to filter queries. InfluxDB queries use `farm_id` tag. The audit found 10 endpoints missing this — 8 fixed, 2 MCMT endpoints skip (in-memory tracker, ephemeral, no farm data).
  - **WebSocket scoping**: Worker broadcasts to both global and farm-specific channels. Frontend subscribes via `?farm_id=` query param.
  - **Camera HLS streaming**: `hls.js` in CameraFeed.tsx targets the Frigate go2rtc HLS endpoint via nginx proxy (`/api/frigate/hls/`), so `X-Farm-ID` and impersonation headers are not needed there.

  ## Next Steps
   1. Test end-to-end: `docker compose up`, add cameras, verify HLS playback + MQTT events + health classification + global_id tracking.
   2. Expand MinIO integration: integrate snapshot saving from Frigate subscriber, add frontend media gallery component.
   3. Write tests for the MinIO media endpoints and the farm_id scoping on the 8 fixed endpoints.
   4. Write frontend tests (Vitest + React Testing Library).

  ## Critical Context
  - `farm_id` is a UUID FK on `users` (nullable — null = super admin), `cameras`, `chickens`, `alerts`, `alert_rules` (NOT NULL on data tables).
  - Chicken IDs are unique per-farm via composite unique constraint `(farm_id, chicken_id)`.
  - `get_farm_id()` dependency resolves farm from JWT (farm users), `X-Farm-ID` header (super admin), or query param (super admin).
  - `require_permission()` checks only the permission string against the role; farm scoping is a separate `get_farm_id()` dependency that filters the SQL.
  - Frontend `localStorage` key `selected_farm_id` drives `X-Farm-ID` header via axios interceptor.
  - Impersonation token stored in `localStorage` as `impersonation_token`; `impersonation_info` stores the target user's details (id, email, name, role, permissions).
  - `hasPermission()` in AuthContext checks `impersonating.permissions` when impersonating, otherwise checks `user.role.permissions`.
  - WebSocket broadcasts use farm-scoped channels (`farm_{id}/detections`), frontend passes `?farm_id=` in the connection URL.
  - MCMT tracker endpoints (`/detection/mcmt/identities`, `/detection/mcmt/gallery/stats`) are intentionally exempt from farm scoping — they expose in-memory ephemeral data with no farm linkage.

  ## Relevant Files
  - `backend/app/auth/router.py`: Impersonate endpoint, register (single super admin guard), delete user (last super admin guard + farm_id check).
  - `backend/app/auth/deps.py`: Authorization header priority over cookie; `get_farm_id()` dependency.
  - `backend/app/auth/service.py`: `"users:impersonate"` in super_admin permissions map.
  - `backend/app/detection/router.py`: Camera ownership checks added to stats/history/summary endpoints.
  - `backend/app/detection/queries.py`: `query_detected_chickens()` now accepts `farm_id` filter.
  - `backend/app/health/router.py`: `GET /health/scores` passes `farm_id`.
  - `backend/app/health/queries.py`: `query_health_scores()` now accepts `farm_id` filter.
  - `backend/app/alerts/router.py`: Ownership checks on acknowledge and rules update.
  - `backend/app/chickens/router.py`: `GET /chickens/detected` passes `farm_id`.
  - `frontend/src/auth/AuthContext.tsx`: `impersonating` state, `startImpersonating()`, `stopImpersonating()`, `hasPermission()` switch.
  - `frontend/src/api/axios.ts`: Impersonation token injection; token refresh updates impersonation_token.
  - `frontend/src/components/ImpersonationBanner.tsx`: Yellow banner with Stop button.
  - `frontend/src/pages/Settings.tsx`: "View as" button per user row; super_admin excluded from role options and delete button.
  - `frontend/src/layout/ResponsiveShell.tsx`: Banner rendered above page content.
  - `frontend/src/hooks/useWebSocket.ts`: Appends `?farm_id=` query param.
   - `docs/architecture.md`: Updated to v4.0 with multi-farm, impersonation, roles table, farm-scoped RBAC, Frigate pipeline.
   - `backend/app/media/client.py`: MinIO client initialization, bucket ensure, CRUD operations with `farms/{farm_id}/` prefix.
   - `backend/app/media/router.py`: Upload/download/delete/list media endpoints with farm_id scoping.
   - `backend/app/media/schemas.py`: Pydantic models for media API responses.
   - `backend/app/frigate/subscriber.py`: MQTT event subscriber, health classification + MCMT ReID trigger.
   - `backend/app/frigate/client.py`: REST client for Frigate API (stats, events, snapshots, recordings).
   - `backend/app/frigate/config_manager.py`: Camera config builder for Frigate YAML.
   - `backend/app/frigate/schemas.py`: Pydantic models for Frigate event/camera config.
   - `backend/app/detection/mcmt_singleton.py`: Shared MCMT GlobalTracker singleton.
   - `backend/app/detection/detector.py`: HealthClassifier (best.pt, 32 classes, no counting).
   - `backend/app/utils.py`: retry_async() with exponential backoff.
   - `backend/tests/frigate/`: 19 tests covering schemas, config_manager, client, subscriber.
   - `.env.example`: MediaMTX vars removed, Frigate + MQTT vars added.
   - `mosquitto/config/mosquitto.conf`: MQTT `password_file` + `allow_anonymous false`.
   - `frontend/nginx.conf`: `auth_request /auth-validate` on HLS/VOD locations.
   - `Caddyfile`: Reverse proxy with auto-TLS via `{$DOMAIN}`.
   - `scripts/backup.sh`: Daily pg_dump + influx backup to MinIO with 14-day retention.
   - `Dockerfile.backup`: Alpine-based backup container with `mc` + `influx` + `pg_dump`.
   - `.github/workflows/deploy.yml`: CI test job + deploy with rollback.
persistent_summary_offset: 0
