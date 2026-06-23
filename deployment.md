# Cloud Server Deployment Guide

This guide provides a step-by-step walkthrough to deploy the Poultry Monitoring System to a cloud server (VPS) running Linux (e.g., Ubuntu).

---

## Prerequisites

- **System Resources**: At least 4 cores CPU and 8GB RAM are recommended (since the app runs AI detection, tracking, and video streams).
- **Storage**: SSD with at least 50GB storage (for video recordings, database history, and models).
- **GPU (Highly Recommended)**: An NVIDIA GPU (e.g., AWS EC2 `g4dn.xlarge`, GCP T4, or runpod instances) for fast real-time bird tracking and health classification.
- **Operating System**: Ubuntu 22.04 LTS or 24.04 LTS.
- **Domain Name**: A public domain pointing to your server's IP address (needed for automated SSL certificates via Caddy).

---

## Step-by-Step Deployment

### Step 1: Install GPU Drivers & NVIDIA Container Toolkit (Optional but Recommended)

If your server has an NVIDIA GPU, follow these steps to enable GPU acceleration in Docker containers. If running on CPU-only, skip to **Step 2**.

#### 1.1 Install NVIDIA Drivers (Ubuntu)
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y ubuntu-drivers-common
sudo ubuntu-drivers install
sudo reboot
```
Verify the installation:
```bash
nvidia-smi
```

#### 1.2 Install Docker & Docker Compose
```bash
# Setup Docker's repository
sudo apt-get install -y ca-certificates curl gnupg
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update

# Install packages
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

#### 1.3 Install NVIDIA Container Toolkit
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

### Step 2: Set Up Environment Variables

Clone the repository to `/opt/poultry` on your server:
```bash
sudo mkdir -p /opt/poultry
sudo chown -R $USER:$USER /opt/poultry
git clone <your-repo-url> /opt/poultry
cd /opt/poultry
```

Create a production `.env` file by copying the template:
```bash
cp .env.example .env
```

Generate secure keys (using `openssl rand -hex 32`) and update the `.env` file:
```env
# --- Server Config ---
DOMAIN=poultry.yourdomain.com
JWT_SECRET=YOUR_SECURE_JWT_SECRET
ENCRYPTION_KEY=YOUR_SECURE_ENCRYPTION_KEY
ENCRYPTION_SALT=YOUR_SECURE_SALT

# --- Database ---
POSTGRES_PASSWORD=YOUR_POSTGRES_PASSWORD
INFLUX_TOKEN=YOUR_INFLUX_API_TOKEN
INFLUX_PASSWORD=YOUR_INFLUXDB_ADMIN_PASSWORD

# --- Super Admin ---
DEFAULT_ADMIN_PASSWORD=YOUR_SECURE_SUPER_ADMIN_PASSWORD

# --- MQTT Setup ---
MQTT_USERNAME=frigate
MQTT_PASSWORD=YOUR_MQTT_SECURE_PASSWORD

# --- SSL & Production Defaults ---
CORS_ORIGINS=https://poultry.yourdomain.com
VITE_API_URL=https://poultry.yourdomain.com
COOKIES_SECURE=true
LOG_LEVEL=WARNING
```

---

### Step 3: Generate MQTT Password File

Mosquitto requires a hashed password file for production authentication. Generate it using Docker:
```bash
docker run --rm -v $(pwd)/mosquitto/config:/config eclipse-mosquitto:2.0.20 \
  mosquitto_passwd -c /config/passwd frigate
```
> [!IMPORTANT]
> You will be prompted to enter a password twice. Enter the **exact** password you set for `MQTT_PASSWORD` in your `.env` file.

---

### Step 4: Configure Docker Secrets (For Strict Production Security)

If deploying with [docker-compose.prod.yml](file:///a:/TVS_1/docker-compose.prod.yml), you must initialize a Docker Swarm to support `external: true` secrets:
```bash
docker swarm init
```
Create the required swarm secrets based on your `.env` values:
```bash
echo "YOUR_POSTGRES_PASSWORD" | docker secret create postgres_password -
echo "YOUR_INFLUX_PASSWORD" | docker secret create influx_password -
echo "YOUR_INFLUX_API_TOKEN" | docker secret create influx_token -
echo "YOUR_MQTT_SECURE_PASSWORD" | docker secret create mqtt_password -
echo "frigate" | docker secret create mqtt_username -
echo "YOUR_JWT_SECRET" | docker secret create jwt_secret -
echo "YOUR_SECURE_ENCRYPTION_KEY" | docker secret create encryption_key -
echo "YOUR_SECURE_SALT" | docker secret create encryption_salt -
echo "YOUR_SECURE_SUPER_ADMIN_PASSWORD" | docker secret create default_admin_password -
echo "YOUR_MQTT_SECURE_PASSWORD" | docker secret create frigate_rtsp_password -
```

---

### Step 5: Start the Container Stack

#### Option A: Single Node Standard Mode (Simple Compose)
Use this if you do not want to use Docker Swarm or external secrets:
```bash
docker compose up -d --build
```

#### Option B: Replicated Production Mode (Docker Swarm Secrets)
Use this for high availability with 2 replicated API/frontend containers and isolated network interfaces:
```bash
# Note: Swarm stack deploys use docker stack deploy instead of compose
docker stack deploy -c docker-compose.yml -c docker-compose.prod.yml poultry
```
Or if running compose locally but wanting the prod overrides:
```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

---

### Step 6: Post-Deployment Verification

Verify all services are up and healthy:
```bash
docker compose ps
```

Test the API health endpoint:
```bash
curl https://poultry.yourdomain.com/api/health
```
*(Should return `{"status":"ok", ...}`)*

Verify GPU compatibility:
```bash
docker compose exec backend python -c "import torch; print('CUDA GPU Available:', torch.cuda.is_available())"
```

---

### Step 7: Configure Tailscale for Multi-Farm Cameras

If your video surveillance feeds live on separate remote locations (different networks or behind NATs), configure Tailscale to route the video data securely to the cloud NVR.

1. **Install Tailscale on Cloud Host**:
   ```bash
   curl -fsSL https://tailscale.com/install.sh | sh
   sudo tailscale up --accept-routes
   ```
2. **Install Tailscale on Farm Subnet Router** (e.g. Raspberry Pi at farm site):
   ```bash
   curl -fsSL https://tailscale.com/install.sh | sh
   sudo tailscale up --advertise-routes=192.168.1.0/24
   ```
   *(Change `192.168.1.0/24` to match the local subnet range of the farm IP cameras)*
3. **Approve Routes**: Open the Tailscale Admin Console, go to your Subnet Router machine settings -> "Edit route settings" -> check "Approve" for the advertised camera subnet.

---

### Step 8: Automated Backups

The automated `backup` container starts automatically and performs:
- **PostgreSQL Database Dump** (`pg_dump`)
- **InfluxDB Time-series Backup**
- **MinIO Media files backup**
- Saved directly to the `poultry_backups` Docker volume with a 14-day retention cycle.

To run a manual backup immediately:
```bash
docker compose exec backup /usr/local/bin/backup.sh
```

To list your available backups:
```bash
docker compose exec backup ls -la /var/opt/poultry/backups/
```

To restore PostgreSQL data from a backup:
```bash
gunzip -c /var/opt/poultry/backups/postgres_2026_xx_xx.sql.gz | docker compose exec -T postgres psql -U poultry -d poultry
```

---

## Security Best Practices Checklist

1. **Port Lockdown**: Ensure the server firewall only permits incoming traffic on ports **80** (HTTP) and **443** (HTTPS). Access to ports **8971** (Frigate Console) and database ports should remain restricted behind a local firewall or Tailscale VPN.
2. **Rate Limiting**: Integrated endpoint rate limiting is active by default in the FastAPI application (20 req/min for write requests).
3. **PWA Assets Caching**: Nginx serves PWA assets (`/sw.js` and `/registerSW.js`) with cache-busting headers (`Cache-Control: no-store`) to ensure rapid propagation of frontend updates.
4. **HLS Protection**: RTSP stream segments are proxied internally through Nginx using an `auth_request` subrequest to backend validation routers, ensuring video segments cannot be requested without a valid authorization header or session cookie.
