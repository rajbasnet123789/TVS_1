# Changelog

All notable changes to this project are documented here. The format is based on [Keep a Changelog](https://keepachangelog.com/).

## v0.2.0 — 2026-07-31

### Added
- **Account & data deletion requests** — any non-admin user can request deletion from Settings → *Delete Account & Data* (optional reason). The account is deactivated and signed out immediately; admins approve (permanent delete) or reject (reactivate) from a *Deletion Requests* panel in Settings. Super admin cannot be deleted.
- **Public privacy policy page** at `/privacy-policy`, linked from the login screen.
- **Count-only mode** — the dashboard shows live per-camera chicken counts (`GET /detection/live-counts`); raw video is relayed through go2rtc HLS (at `:1984`, host network) instead of being streamed by default.
- **Per-channel live counts** on the dashboard overview.

### Changed
- `useLiveCounts` is now a **global singleton** — one shared 3-second poll loop for the whole app instead of one per camera card (fewer requests, consistent data).
- GPU acceleration enforced for all YOLO/CV work (CUDA + FP16).
- Login rate limiter removed (was causing intermittent login failures).

### Fixed
- Session loss on refresh (cookie `path=/`, refresh endpoint response).
- `/auth/refresh` 500 crash (`must_change_password` missing from token response).
- Intermittent 401 logins (email now normalized: trimmed + lowercased).
- Chicken count always showing 0; backend health-check timeout.
- Duplicate cameras and wrong RTSP URL mapping producing the same stream on all feeds.
- Dashboard now uses the shared `useCameras()` hook instead of an independent fetch.

### Security
- go2rtc un-exposed from the public reverse proxy; internal-only now.

## v0.1.0 — 2026-07-28

### Added
- go2rtc NVR stream proxy integration (`go2rtc/` service, HLS API `:1984`, RTSP relay `:8554`).
- Native DVRIP multi-channel ingestion for the TVS NVR (`dvrip://...:34567?channel=N&subtype=0`) with FFmpeg RTSP-TCP primary + DVRIP fallback producers; static streams `ch0..ch15`.
- XMEye LAN camera discovery.
- Internal maintenance endpoints: `/v1/internal/reset-cameras`, `/v1/internal/fix-channels`, `/v1/internal/reset-user-password`, `/v1/internal/cameras/status`, `/v1/internal/cameras`.
- `POST /nvr/connect`, `POST /nvr/discover`, `POST /nvr/register`.

### Changed
- Stream architecture aligned to TVS NVR (DVRIP `:34567`) → go2rtc (`:554`) → cv-engine pipeline.
- Camera feed now has an HTTP JPEG-stream fallback for networks where WebSocket stalls.

### Fixed
- go2rtc stream registration now uses PUT with proper query params (POST fallback) and re-registers on every sync loop.
- NVR connection errors handled gracefully; distinct channel URLs (0..15) saved on register.
- WebSocket upgrade headers corrected; duplicate go2rtc registration logs eliminated.
- MJPEG/WebSocket nginx proxy locations aligned to the running architecture.

### Removed
- Legacy Scan XMEye/DVRIP button and dialog from the Live Feed page.

## Earlier history

The initial system (Frigate-based, per-chicken ReID, health classification, MinIO) predates the current count-only architecture. See the git history for those changes; they are no longer present in the codebase.
