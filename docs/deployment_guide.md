# Deployment Guide: Deploying to a GPU Instance

This guide explains how to deploy the Poultry Monitoring System to a cloud virtual machine equipped with an NVIDIA GPU (such as AWS EC2 `g4dn.xlarge`, GCP `n1-standard-4` with T4, or any server with an NVIDIA GPU).

---

## Step 1: Install NVIDIA Driver & Docker on the Instance

### 1.1 Install NVIDIA Drivers (Ubuntu)

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y ubuntu-drivers-common
sudo ubuntu-drivers install
sudo reboot
```

Verify:
```bash
nvidia-smi
```

### 1.2 Install Docker & Docker Compose

```bash
sudo apt-get install -y ca-certificates curl gnupg
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update && sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

### 1.3 Install NVIDIA Container Toolkit

```bash
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
  sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
  sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
```

---

## Step 2: Production Override

The project ships with `docker-compose.prod.yml` that:

- **Removes all dev port exposures** — internal services (Postgres, Redis, InfluxDB, backend, frontend) are only reachable within the Docker network
- **Enables Docker Swarm secrets** — passwords and tokens are mounted as files instead of env vars
- **Sets production env vars** — `COOKIES_SECURE=true`, `LOG_LEVEL=WARNING`
- **Enables horizontal scaling** — `backend` and `frontend` services set `replicas: 2`

Use it alongside the base compose file:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

### Docker Swarm Secrets

Before deploying, create Docker secrets for all sensitive values:

```bash
# Create secrets (one per line)
echo "<postgres-password>" | docker secret create postgres_password -
echo "<influx-password>" | docker secret create influx_password -
echo "<influx-token>" | docker secret create influx_token -
echo "<frigate-rtsp-password>" | docker secret create frigate_rtsp_password -
echo "<mqtt-username>" | docker secret create mqtt_username -
echo "<mqtt-password>" | docker secret create mqtt_password -
```

Alternatively, skip secrets and use the base compose alone:

```bash
docker compose up -d --build
```

### GPU Acceleration

The `backend` and `frigate` services use GPU acceleration. The docker-compose.yml already has the `deploy.resources` block for GPU. Verify it's set for the `backend` service:

```yaml
  backend:
    build:
      context: .
      dockerfile: Dockerfile
      target: backend
    runtime: nvidia
    deploy:
      resources:
        limits:
          cpus: '4'
          memory: 4G
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]
```

---

## Step 3: Set Up Production Environment Variables (`.env`)

Copy `.env.example` to `.env` and fill in all values:

```bash
cp .env.example .env
```

Required values (generate with `openssl rand -hex 32`):

| Variable | Description | Example |
|----------|-------------|---------|
| `DOMAIN` | Your production domain name | `poultry.example.com` |
| `POSTGRES_PASSWORD` | Postgres database password | `<random 32 hex>` |
| `INFLUX_TOKEN` | InfluxDB API token | `<random 32 hex>` |
| `INFLUX_PASSWORD` | InfluxDB admin password | `<your-password>` |
| `JWT_SECRET` | JWT signing secret | `<random 32 hex>` |
| `ENCRYPTION_KEY` | Encryption key for sensitive data | `<random 32 hex>` |
| `DEFAULT_ADMIN_PASSWORD` | Default super admin login password | `<your-password>` |
| `MQTT_USERNAME` | Mosquitto MQTT username | `frigate` |
| `MQTT_PASSWORD` | Mosquitto MQTT password | `<your-password>` |
| `SENTRY_DSN` | Sentry DSN for error tracking (leave blank to disable) | `https://...@...ingest.sentry.io/...` |

Production overrides from defaults:

| Variable | Production Value | Reason |
|----------|-----------------|--------|
| `CORS_ORIGINS` | `https://your-domain.com` | Lock CORS to your domain |
| `VITE_API_URL` | `https://your-domain.com` | Frontend API base URL |
| `LOG_LEVEL` | `WARNING` | Reduce log noise |
| `COOKIES_SECURE` | `true` | Required for HTTPS |
| `BACKUP_INTERVAL_HOURS` | `24` | Daily automated backups |
| `BACKUP_RETENTION_DAYS` | `14` | Keep 14 days of backups |

---

## Step 4: Tailscale Setup (Multi-Farm Camera Connectivity)

If you have cameras on **separate networks** (different farm sites, different VLANs), Tailscale creates an encrypted mesh VPN so the GPU server can reach every camera by its local IP without opening firewall ports.

### 4.1 Install on GPU Server (Docker Host)

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up --authkey=$TAILSCALE_AUTH_KEY --accept-routes
```

That's it — no Docker config changes. Containers use the host's routing table.

### 4.2 Install at Each Farm Site (Subnet Router)

Each farm needs a small Linux device on the same LAN as its cameras (Raspberry Pi, old laptop, or the NVR itself):

```bash
# 1. Install Tailscale
curl -fsSL https://tailscale.com/install.sh | sh

# 2. Enable IP forwarding
echo 'net.ipv4.ip_forward = 1' | sudo tee /etc/sysctl.d/99-tailscale.conf
echo 'net.ipv6.conf.all.forwarding = 1' | sudo tee -a /etc/sysctl.d/99-tailscale.conf
sudo sysctl -p /etc/sysctl.d/99-tailscale.conf

# 3. Advertise the camera subnet
sudo tailscale up --authkey=$TAILSCALE_AUTH_KEY --advertise-routes=192.168.1.0/24
```

Replace `192.168.1.0/24` with the actual subnet where cameras live at that farm.

### 4.3 Approve Routes

In the Tailscale admin console (`https://login.tailscale.com/admin/machines`), find each farm node and click **"..." → "Edit route settings"** → check **"Approve"** for the advertised subnet.

### 4.4 Verify

```bash
# From the GPU server — this should reach a camera at Farm A
ping 192.168.1.50

# If ping works, Frigate can use rtsp://192.168.1.50:554/stream1
# with zero changes to the Docker stack
```

### 4.5 Remote Dashboard Access (Optional)

Instead of opening firewall ports, expose the web UI via Tailscale Serve:

```bash
sudo tailscale serve --bg --https=443 http://localhost:3000
```

Now accessible at `https://poultry-gpu-server.tailXXXXX.ts.net/` — only your tailnet can reach it.

---

## Step 5: Generate MQTT Password File

Mosquitto requires a password file for authenticated access. Generate it **before** starting the stack:

```bash
# Create the password file for the 'frigate' user
docker run --rm -it -v $(pwd)/mosquitto/config:/config eclipse-mosquitto:2.0.20 \
  mosquitto_passwd -c /config/passwd frigate

# You will be prompted for a password — use the same value as MQTT_PASSWORD in .env
```

This creates `mosquitto/config/passwd` which is referenced by `mosquitto.conf`.

---

## Step 6: Deploy

```bash
# Clone or copy the project to the server
cd /opt/poultry

# Build and launch all services (production mode)
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

For single-host without secrets (simpler):

```bash
docker compose up -d --build
```

This starts all services: Postgres, Redis, InfluxDB, Mosquitto, Frigate, backend, frontend, Caddy (TLS proxy), and backup scheduler.

Verify:
```bash
# Health check
curl http://localhost:8000/health
# → {"status":"ok","frigate":"connected","version":"0.1.0",...}

# Frigate stats
curl http://localhost:5000/api/stats

# Run a manual backup to verify the backup service works
docker compose exec backup /usr/local/bin/backup.sh
```

---

## Step 7: Firewall / Security Group

When using `docker-compose.prod.yml`, all dev ports are automatically removed. Only these ports exit the container network:

| Port | Service | Access |
|------|---------|--------|
| 80 | Caddy (HTTP — redirects to HTTPS) | Internet |
| 443 | Caddy (HTTPS) | Internet |
| 8971 | Frigate UI | Admin/VPN only |
| 1883 | Mosquitto MQTT | Admin/VPN only (if external clients need it) |

Without the production override, also block these from the internet:

| Port | Service | Access |
|------|---------|--------|
| 5433 | PostgreSQL | ❌ Block |
| 6379 | Redis | ❌ Block |
| 8086 | InfluxDB | ❌ Block |

| 8000 | Backend API | ❌ Block |
| 3000 | Frontend (dev) | ❌ Block |
| 5000 | Frigate API | ❌ Block |
| 1984 | go2rtc | ❌ Block |
| 8555/udp | Frigate WebRTC | ❌ Block |

---

## Step 8: TLS with Reverse Proxy

The `docker-compose.yml` includes a **Caddy** service by default that handles TLS automatically:

- Set `DOMAIN=your-domain.com` in `.env`
- Caddy auto-provisions Let's Encrypt certificates
- All traffic is proxied from Caddy → frontend (nginx) → backend

The `Caddyfile` at the project root:
```
{$DOMAIN:localhost} {
    reverse_proxy frontend:80
}
```

When `DOMAIN` is set to a real domain, Caddy automatically fetches trusted TLS certificates. When `DOMAIN=localhost` (default), Caddy falls back to self-signed certificates (for development).

### Alternative — Cloudflare Tunnel (no open ports)

```bash
docker run cloudflare/cloudflared tunnel --no-autoupdate run --token YOUR_TOKEN
```

This tunnels traffic to your domain without opening any inbound firewall ports.

---

## Step 9: First-Time Setup

1. Visit `https://your-domain.com`
2. Log in as `admin@poultry.farm` with your `DEFAULT_ADMIN_PASSWORD`
3. Go to **Admin → Farms** → create your first farm
4. Go to **Settings → Users** → create users (assign to farm)
5. Go to **Cameras → Add Camera** → enter RTSP URL
6. Cameras appear in **Live Feed** via Frigate HLS (~2-3s latency)

---

## Step 10: Verify GPU Acceleration

```bash
docker compose exec backend python -c "import torch; print('GPU:', torch.cuda.is_available())"
```

For Frigate TensorRT/OpenVINO GPU acceleration, see the Frigate docs on configuring the detector.

---

## Step 11: Post-Deployment Verification

### HLS Stream Authentication

Live HLS feeds are protected by nginx `auth_request` — every HLS segment request is validated against the backend's `/auth/validate-token` endpoint. Both cookie-based sessions (non-impersonated) and `Authorization: Bearer` header (impersonation tokens) are supported.

To verify:
```bash
# Without a token — should return 401
curl -v https://your-domain.com/api/frigate/hls/cam1/index.m3u8 2>&1 | grep "401"

# With a valid token — should return 200
curl -H "Authorization: Bearer $(your-jwt-token)" \
  https://your-domain.com/api/frigate/hls/cam1/index.m3u8 -o /dev/null -w "%{http_code}"
```

### Rate Limiting

All write endpoints (POST/PUT/DELETE) are rate-limited to **20 requests per minute** per IP. Auth endpoints have stricter limits (10/minute on login). Read endpoints are currently unthrottled but can be enabled by adding `@limiter.limit("60/minute")` to GET handlers.

### Automated Backups

The `backup` service runs automatically every 24 hours (configurable via `BACKUP_INTERVAL_HOURS`). It:

1. Dumps Postgres via `pg_dump`, compresses with gzip
2. Exports InfluxDB via `influx backup`
3. Stores both in the `poultry_backups` Docker volume at `/var/opt/poultry/backups`
4. Prunes backups older than `BACKUP_RETENTION_DAYS` (default: 14)

To trigger an immediate backup:
```bash
docker compose exec backup /usr/local/bin/backup.sh
```

To restore from a backup:
```bash
# List available backups
docker compose exec backup ls /var/opt/poultry/backups/

# Restore Postgres
gunzip -c /var/opt/poultry/backups/postgres_20250101_120000.sql.gz | docker compose exec -T postgres psql -U poultry

# Restore InfluxDB (requires manual influx CLI restore)
```

---

## Step 12: CI/CD Pipeline (Optional)

The project includes a GitHub Actions workflow (`.github/workflows/deploy.yml`) that:

1. **Test** — Runs `pytest` against a fresh Postgres service container, then builds the frontend (TypeScript check + vite build)
2. **Build & Push** — Builds backend and frontend Docker images, pushes to GitHub Container Registry
3. **Deploy** — SSHes into the production server, pulls new images, and performs a zero-downtime deploy with automatic rollback on health check failure

To enable:
1. Set repository secrets: `DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_SSH_KEY`
2. Push to the `main` branch

---

## Step 13: Security Checklist

| Area | Status | Notes |
|------|--------|-------|
| **MQTT authentication** | ✅ Built-in | `password_file` in mosquitto.conf, credentials passed to Frigate + subscriber |
| **HLS stream auth** | ✅ Built-in | nginx `auth_request` validates JWT on every segment request |
| **HTTPS / TLS** | ✅ Built-in | Caddy service with auto Let's Encrypt via `DOMAIN` env var |
| **Super admin enforcement** | ✅ Built-in | Single `admin@poultry.farm`, cannot create/delete another |
| **Farm data isolation** | ✅ Built-in | `farm_id` FK on 5 tables, scoped queries, farm-scoped WebSocket channels |
| **Rate limiting** | ✅ Built-in | 20/min on all write endpoints, 10/min on login |
| **Error monitoring** | ⚙️ Optional | Set `SENTRY_DSN` in `.env` to enable |
| **Automated backups** | ✅ Built-in | Daily backup service (Postgres + InfluxDB + media), configurable interval + retention |
| **Tailscale VPN** | ✅ Documented | Host-level install, subnet routing for multi-farm cameras, optional Tailscale Serve for dashboard |
| **Model integrity** | ✅ Built-in | SHA-256 checksum verified on health model load |
| **JWT security** | ✅ Built-in | 15-min access tokens, 7-day refresh with rotation and theft detection |
| **Impersonation security** | ✅ Built-in | 15-min hardcoded expiry, farm-scoped, yellow banner UI |
| **CORS** | ✅ Built-in | Strips whitespace, locked to configured origins |
| **Container security** | ✅ Built-in | Non-root user in containers, resource limits, health checks on all services |

---

**Architecture note:** Frigate handles all RTSP ingestion, motion-triggered bird detection, recording, and HLS streaming. The backend's Frigate subscriber processes bird detection events via MQTT, runs health classification (best.pt, 32 classes) and MCMT re-identification (MiewID + FAISS), and broadcasts results in real time over WebSocket.
