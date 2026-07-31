# TODO

Statuses: `[ ]` open · `[~]` in progress · `[x]` done.

## CV pipeline

- [x] Count-only mode (YOLOv8 per-camera subprocesses) with go2rtc HLS relay (`:1984`, host network)
- [ ] Embed go2rtc HLS in the dashboard (the SPA currently renders count cards only; raw video is viewed directly on `:1984`)
- [x] CUDA + FP16 GPU enforcement for YOLO/CV ops
- [ ] **Health scoring** — cv-engine does not write to the InfluxDB `health` measurement yet; `health` endpoints return empty. Requires a health classifier/rule source.
- [ ] Per-chicken identity / re-identification (MCMT/ReID) — intentionally removed; revisit only if a client needs cross-camera identity tracking.
- [ ] MQTT consumers — Mosquitto is deployed but nothing subscribes/publishes yet (reserved).

## Backend

- [x] Account & data deletion request flow (model + migration 005 + endpoints + admin UI)
- [x] `PUT /auth/users/{id}` updates `full_name`
- [x] WebSocket token from `?token=` query param
- [x] Internal endpoints guarded by `X-Internal-Token` (`CV_ENGINE_API_KEY`)
- [ ] **Set `CV_ENGINE_API_KEY` in production `.env`** (`openssl rand -hex 32`) — currently soft-gated in dev; required in prod.
- [ ] Make the backend test suite green in CI — verify `test_media.py`, `test_farm_scoping.py`, `test_deletion_request.py`, `test_api.py` all pass against the Postgres service container; the old `tests/frigate/` reference in `.opencode/plans/fix-register-influxdb-errors.md` is stale.
- [ ] Add tests for the `nvr` module (Dahua CGI + ONVIF discovery mocks).

## Frontend

- [ ] Wire Vitest + React Testing Library into CI (`npm run test` currently exists but isn't a CI gate).
- [ ] Add unit tests for `useLiveCounts` singleton and `AuthContext` impersonation state.
- [ ] Add tests for the Settings deletion-request panel (Approve/Reject flows).

## Infra / ops

- [x] `docker-compose.prod.yml` hardening (ports closed, `DEBUG=false`, `ENVIRONMENT=production`)
- [x] Backend single-worker enforcement (`assert_single_worker()`)
- [x] Backup service (daily pg_dump + InfluxDB, 14-day retention)
- [ ] Document + verify the Alembic stamp flow on fresh prod DBs (`alembic stamp 004` then `upgrade head`) — see [deployment.md](deployment.md).
- [ ] Consider adding `cv-engine` image build to the CI `deploy.yml` (currently built on the server from source).
