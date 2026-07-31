# TVS Poultry Monitor — Server Runbook & Updates

Day-to-day operations for the running server. For first-time cloud deployment, see [docs/deployment_guide.md](docs/deployment_guide.md).

---

## Updating the app (the daily flow)

The deploy model is **git pull on the server + rebuild affected containers** (no Caddy, no Swarm, no image registry for the running stack).

```bash
cd /opt/poultry                 # repo location on the server (the live server currently uses ~/TVS_1)
git pull origin main

# Apply database migrations (if the update included any — see below)
docker compose exec backend alembic upgrade head

# Rebuild and restart everything (or only what changed)
docker compose up -d --build

# For a frontend-only change:
docker compose build frontend && docker compose up -d frontend

# For backend-only:
docker compose build backend && docker compose up -d backend

# For cv-engine:
docker compose build cv-engine && docker compose up -d cv-engine
```

After a frontend deploy, tell users to hard-refresh once (Ctrl+Shift+R) so the new bundle isn't masked by a cached `index.html`.

### Database migrations

- New schema changes arrive as Alembic migrations in `backend/alembic/versions/`.
- Because the backend also auto-creates tables at startup (`create_all`), the app usually survives without running Alembic — but **always run** `alembic upgrade head` after an update that touches the schema so the version history stays in sync.
- **Gotcha:** if the DB was created purely by `create_all` (empty Alembic version table), a bare `upgrade head` replays *all* migrations and fails with `DuplicateColumnError: column "pos_x" ... already exists`. Fix:

```bash
docker compose exec backend alembic stamp 004     # mark existing schema as revision 004
docker compose exec backend alembic upgrade head  # then apply 005+
```

Confirm: `docker compose exec backend alembic current` should print `005`.

---

## Service management

```bash
docker compose ps                     # status of all services
docker compose logs -f backend        # backend logs
docker compose logs -f cv-engine      # detection pipeline logs
docker compose logs -f frontend       # nginx/SPA logs
docker compose restart backend        # restart one service
docker compose up -d                  # start/refresh everything
docker compose down                   # stop (keeps volumes)
docker compose down -v                # stop + delete volumes (destructive)
```

### Service ports on the host

| Port | Service | Notes |
|------|---------|-------|
| 3001 | frontend | nginx/SPA + API proxy (localhost only in prod) |
| 18000 | backend | FastAPI (localhost only) |
| 8700 | cv-engine | host network, detection pipeline |
| 1984 / 8554 | go2rtc | HLS API / RTSP relay (host network) |
| 5433 / 8086 / 6379 / 1883 | postgres / influxdb / redis / mosquitto | internal — don't expose |

---

## Backups & restore

Backups run automatically (default: every 24h, 14-day retention) into the `poultry_backups` volume.

```bash
# Trigger a manual backup
docker compose exec backup /usr/local/bin/backup.sh

# List backups
docker compose exec backup ls -la /var/opt/poultry/backups/

# Restore Postgres
gunzip -c /var/opt/poultry/backups/postgres_<timestamp>.sql.gz | docker compose exec -T postgres psql -U poultry -d poultry
```

---

## Rollback

If a deploy breaks:

```bash
# Option A: revert the code and rebuild
git checkout <previous-commit>
docker compose up -d --build

# Option B: restart the previous containers (if still present)
#   find the image id, retag, and `docker compose up -d`
```

The CI deploy workflow (`deploy.yml`) automates Option B for backend/frontend with a health-check rollback.

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `alembic upgrade head` fails with `DuplicateColumnError` | DB was created by `create_all`; `alembic stamp 004` then `upgrade head` (see above) |
| Camera shows offline | Check `docker compose logs cv-engine`; verify the camera IP is reachable from the server (`ping <cam-ip>`); confirm go2rtc is ingesting (`curl http://localhost:1984/api/streams`) |
| Counts stuck at 0 | cv-engine needs a GPU or will run slow on CPU (`docker compose logs cv-engine`); confirm InfluxDB bucket `detections` is receiving writes |
| Backend won't start | `assert_single_worker()` aborts if `WORKERS`/`UVICORN_WORKERS` > 1 — remove any multi-worker env |
| go2rtc HLS not reachable | go2rtc runs on the host network; probe with `curl http://localhost:1984/api/streams` and confirm the camera record's URL matches a go2rtc stream. The SPA is count-first — raw video is viewed directly on `:1984` |
| 504 timeouts on slow responses | Backend is single-worker by design; check CPU/GPU saturation with `docker stats` |
| Frontend serves stale UI | Hard-refresh; verify the `frontend` container was rebuilt (`docker compose build frontend`) |
