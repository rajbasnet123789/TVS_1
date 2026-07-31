# Contributing to TVS Poultry Monitor

## Repository layout

```
backend/          FastAPI REST API + WebSocket (SQLAlchemy async, Alembic migrations)
cv_engine/        YOLOv8 + OpenCV + FFmpeg detection pipeline (FastAPI, GPU)
frontend/         React + TypeScript + Vite + MUI dashboard (nginx in prod)
go2rtc/           go2rtc config — static NVR channel streams
docs/             Architecture, deployment, and localhost guides
models/           ML model metadata + weights
```

## Development setup

1. Copy `.env.example` → `.env` and fill in the secrets.
2. Start the infra + stack:

   ```bash
   docker compose up -d --build
   ```

   Frontend: http://localhost:3001 · Backend API: http://localhost:18000/docs

3. Or run pieces natively — see [docs/localhost-development-guide.md](docs/localhost-development-guide.md).

## Making changes

- **Branch discipline:** work on a feature branch off `main`; the deploy pipeline (`.github/workflows/deploy.yml`) runs on pushes to `main`.
- **Backend** (`backend/`):
  - Uses async SQLAlchemy + FastAPI. Follow existing module layout (`app/<feature>/router.py`, `schemas.py`, `models.py`).
  - Schema changes must include an Alembic migration in `backend/alembic/versions/` (chain: `001_mcmt` → `001` → `002` → `003` → `004` → `005`; new revisions point at the current head).
  - All data endpoints must stay farm-scoped via the `get_farm_id()` dependency.
  - The backend must run as a **single Uvicorn worker** — never ship multi-worker config.
- **cv-engine** (`cv_engine/`): per-camera subprocesses; the main service stays on the host network. Internal calls to the backend use `X-Internal-Token: {CV_ENGINE_API_KEY}`.
- **Frontend** (`frontend/`): React + TS + MUI. Keep shared state in the existing global hooks (`useCameras`, `useLiveCounts`) instead of per-component fetches.

## Verification (run before pushing)

```bash
# Backend: tests (needs Postgres; tests that can't run will skip)
cd backend
pytest -v

# Frontend: type-check + production build
cd frontend
npm run build

# Frontend: unit tests
npm run test

# Lint (optional but nice)
pre-commit run --all-files     # ruff + prettier
```

CI runs `pytest -x` against a fresh Postgres service container and `npm run build`.

## Pull requests

- Title should start with the change kind, e.g. `feat:`, `fix:`, `refactor:`, `security:`.
- Describe what users can do after the change and anything that needs a DB migration or a frontend hard-refresh.
- If the PR adds a migration, note the `alembic upgrade head` step in the description.
- After merge, the deploy workflow builds and deploys backend/frontend automatically; cv-engine changes are built on the server (`docker compose build cv-engine && docker compose up -d cv-engine`).

## Docs

Keep the docs in sync with behavior changes:

- `README.md` — features, quick start, structure
- `docs/architecture.md` — how the pieces fit together
- `deployment.md` / `docs/deployment_guide.md` — server operations
- `CHANGELOG.md` — user-visible changes per release
- `TODOS.md` — outstanding work

## Commit conventions

- Write clear, single-purpose commits.
- Don't commit secrets, `.env`, or model weights.
- This repo uses `main` as the base branch; do not push directly to `main` without a review.
