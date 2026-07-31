# TVS Poultry Monitor — Deployment Guide

This guide covers deploying the full stack to a Linux server (Ubuntu 22.04/24.04) with an NVIDIA GPU.

> **Ongoing updates / day-to-day server work:** see [deployment.md](../deployment.md) (git-pull deploy, alembic migrations, rollback).

---

## 1. Prerequisites

- **Hardware:** 4+ cores, 8 GB+ RAM, SSD with 50 GB+ free. An NVIDIA GPU (4 GB VRAM+) is recommended for real-time counting; CPU works but is slower.
- **OS:** Ubuntu 22.04 LTS or 24.04 LTS.
- **Domain / access:** a DNS domain for HTTPS, or Tailscale for VPN-only access.
- **Tailscale account** (recommended) so the server can reach farm cameras on remote subnets.

---

## 2. Install Docker & the NVIDIA Container Toolkit

```bash
# Docker
sudo apt-get update && sudo apt-get install -y ca-certificates curl gnupg
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update && sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# NVIDIA drivers
sudo apt install -y ubuntu-drivers-common
sudo ubuntu-drivers install && sudo reboot

# NVIDIA Container Toolkit (for cv-engine GPU passthrough)
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
  sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
  sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker

# Verify
nvidia-smi
```

---

## 3. Tailscale (multi-farm camera reachability)

The server must reach each farm's cameras over LAN IPs, so put the server and each farm site on one tailnet.

```bash
# On the server
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up --accept-routes

# At each farm site, on a device on the camera LAN (subnet router)
echo 'net.ipv4.ip_forward = 1' | sudo tee /etc/sysctl.d/99-tailscale.conf
sudo sysctl -p /etc/sysctl.d/99-tailscale.conf
sudo tailscale up --advertise-routes=192.168.31.0/24   # camera subnet

# Approve the advertised routes in the Tailscale admin console.
# Verify from the server:
ping 192.168.31.169
```

**Why this matters:** `cv-engine` and `go2rtc` run with `network_mode: host`, so they use the host's routing table — including Tailscale routes. Docker bridge NAT would block Tailscale-routed subnets.

---

## 4. Configure `.env`

```bash
cd /opt/poultry           # or wherever you cloned the repo
cp .env.example .env
```

Generate secrets with `openssl rand -hex 32` and fill in every `<change-me>`:

| Variable | Notes |
|----------|-------|
| `DOMAIN` | e.g. `coop.tvssecurity.com`; used for `VITE_API_URL` and `CORS_ORIGINS` |
| `POSTGRES_PASSWORD` | Postgres password |
| `INFLUX_PASSWORD`, `INFLUX_TOKEN` | InfluxDB admin password + API token |
| `JWT_SECRET`, `ENCRYPTION_KEY`, `ENCRYPTION_SALT` | Security secrets |
| `DEFAULT_ADMIN_PASSWORD` | Initial password for `admin@poultry.farm` |
| `CV_ENGINE_API_KEY` | **Required in production.** `openssl rand -hex 32`. Shared between backend and cv-engine for `/v1/internal/*` calls |
| `RTSP_PASSWORD` | Password for camera RTSP/DVRIP streams |
| `MQTT_USERNAME`, `MQTT_PASSWORD` | Mosquitto credentials (currently unused by code, reserved) |
| `CORS_ORIGINS`, `VITE_API_URL` | `https://<DOMAIN>` in production |
| `COOKIES_SECURE` | `true` over HTTPS |
| `LOG_LEVEL`, `DEBUG`, `ENVIRONMENT` | `WARNING`, `false`, `production` in production |
| `GOOGLE_CLIENT_ID` | Optional Google OAuth client ID |

---

## 5. Deploy

```bash
docker compose up -d --build
```

This starts: `postgres`, `influxdb`, `redis`, `mosquitto`, `go2rtc`, `cv-engine`, `backend`, `frontend`, `backup`.

### Database migrations (important — first deploy)

The backend auto-creates missing tables at startup (`Base.metadata.create_all`), so the app works even when Alembic was never run. If you deploy a schema change that ships as a migration, run:

```bash
docker compose exec backend alembic current          # what Alembic thinks is applied
docker compose exec backend alembic upgrade head     # apply pending migrations
```

**If the DB was previously created only by `create_all`** (Alembic version table empty), Alembic will try to replay all migrations from scratch and fail with `DuplicateColumnError`. Fix by stamping at the last applied revision, then upgrading:

```bash
docker compose exec backend alembic stamp 004        # mark 001_mcmt..004 as applied
docker compose exec backend alembic upgrade head     # apply only 005+
```

> If unsure what revision to stamp at, check `docker compose exec backend alembic heads` and inspect which schema objects already exist.

---

## 6. Verify

```bash
docker compose ps                                    # all services healthy/running
curl -s http://localhost:18000/health                # {"status":"ok"}
curl -s http://localhost:8700/health                 # cv-engine: {"status":"ok"}
curl -s http://localhost:8700/status                 # per-camera worker status
```

### First-time setup

1. Open the dashboard (https://`<DOMAIN>`/ or `http://<server-ip>:3001`).
2. Log in as `admin@poultry.farm` with `DEFAULT_ADMIN_PASSWORD`.
3. **Admin → Farms** → create farms.
4. **Settings → Users** → create users and assign them to farms.
5. **Cameras** → add cameras (enter RTSP/DVRIP URLs, or use ONVIF/XMEye discovery, or NVR register).
6. Counts appear on the Dashboard. To view raw camera video, open go2rtc's HLS at `http://<host>:1984` (the SPA itself is count-first).

---

## 7. Security Checklist

| Area | Status | Notes |
|------|--------|-------|
| Public surface | ✅ | Only `frontend:80` is exposed; all other ports are host-bound or internal |
| HTTPS | ✅ | Terminated by Tailscale Serve / reverse proxy in front of the host; frontend nginx serves plain HTTP |
| Internal API | ✅ | `/v1/internal/*` guarded by `CV_ENGINE_API_KEY` (must be set in prod) |
| Rate limiting | ✅ | 20/min writes, 10/min login |
| Single super admin | ✅ | `admin@poultry.farm`, cannot be duplicated/deleted |
| Farm isolation | ✅ | `farm_id` FK + scoped queries + farm-scoped WebSocket channels |
| Token security | ✅ | 15-min access + rotating refresh cookie; impersonation tokens override via Bearer header |
| Media | ✅ | Farm-scoped local paths, path-traversal protection |
| Backups | ✅ | Daily Postgres + InfluxDB, 14-day retention |
| Tailscale | ✅ | VPN for multi-farm camera subnets; no public camera ports |

**Firewall reminder:** do **not** expose these to the internet — 5433 (Postgres), 6379 (Redis), 8086 (InfluxDB), 1883 (MQTT), 18000 (backend), 8700 (cv-engine), 1984/8554 (go2rtc), 3001 (frontend host port). Reach them via Tailscale/localhost only.

---

## 8. CI/CD (optional)

`.github/workflows/deploy.yml` runs on pushes to `main`:

1. **test** — `pytest` against a Postgres service container + frontend `npm run build` (type check).
2. **build-and-push** — builds backend + frontend images to GHCR.
3. **deploy** — SSHes to the server (`secrets.DEPLOY_HOST/_USER/_SSH_KEY`), pulls new images, and rolls back if health checks fail.

> Note: the workflow builds backend + frontend images only (cv-engine is built on the server from source).
