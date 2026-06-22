# Poultry Monitoring System — Architecture Document

> **Client:** Poultry Farm Management  
> **Project:** AI-Powered Chicken Monitoring & Health Analysis System  
> **Version:** 1.0

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [How It Works — End to End](#2-how-it-works--end-to-end)
3. [Architecture Layers](#3-architecture-layers)
   - [3.1 Camera Layer](#31-camera-layer)
   - [3.2 Video Processing Layer](#32-video-processing-layer)
   - [3.3 AI Inference Pipeline](#33-ai-inference-pipeline)
   - [3.4 Health Analysis Engine](#34-health-analysis-engine)
   - [3.5 Backend API Layer](#35-backend-api-layer)
   - [3.6 Frontend Dashboard](#36-frontend-dashboard)
   - [3.7 Data Storage Layer](#37-data-storage-layer)
4. [How Chickens Are Identified](#4-how-chickens-are-identified)
5. [Health Scoring System](#5-health-scoring-system)
6. [Alert System](#6-alert-system)
7. [Database Design](#7-database-design)
8. [API Endpoints](#8-api-endpoints)
9. [Frontend Screens](#9-frontend-screens)
10. [Technology Stack](#10-technology-stack)
11. [Deployment Architecture](#11-deployment-architecture)
12. [Implementation Roadmap](#12-implementation-roadmap)
13. [Edge Cases & How We Handle Them](#13-edge-cases--how-we-handle-them)
14. [Security Architecture](#14-security-architecture)
15. [MLOps Pipeline](#15-mlops-pipeline)
16. [Observability & Monitoring](#16-observability--monitoring)
17. [Backup & Disaster Recovery](#17-backup--disaster-recovery)
18. [Network Architecture](#18-network-architecture)
19. [External Integrations](#19-external-integrations)
20. [User Roles & Device Support](#20-user-roles--device-support)
21. [Performance Benchmarks & Targets](#21-performance-benchmarks--targets)
22. [Operations & Maintenance](#22-operations--maintenance)
23. [Cost Estimation](#23-cost-estimation)
24. [Privacy & Compliance](#24-privacy--compliance)
25. [Next Steps & Client Action Items](#25-next-steps--client-action-items)

---

## 1. System Overview

The Poultry Monitoring System is a **multi-farm, web-based application** that uses AI cameras to automatically:

- **Detect** every chicken in the coop in real time
- **Identify** each individual chicken by name/ID
- **Track** movement and behavior across cameras
- **Monitor health** through visual analysis and optional IoT sensors
- **Alert** farm staff when a chicken shows signs of illness or distress
- **Report** trends and analytics over days, weeks, and months
- **Manage multiple farms** from a single dashboard (company-level super admin)

The system processes live video from 5–20 IP cameras installed in each poultry house, runs AI models on each frame, and displays everything on an easy-to-read web dashboard accessible from any device.

### Multi-Farm Architecture

The system supports **multiple independent farms** under a single company account:

- Each farm has its own cameras, chickens, users, alerts, and settings — fully isolated
- Farm users (viewer/operator/admin) are scoped to exactly one farm
- A **super admin** sits above all farms and can view/manage any farm from one dashboard
- Super admin uses a **farm switcher** dropdown to navigate between farms
- Super admin can **impersonate** any user to see exactly what they see

---

## 2. How It Works — End to End

Here is a simple walkthrough of what happens when a chicken walks in front of a camera:

```
 ┌─────────────────────────────────────────────────────────────────────────┐
 │                  END-TO-END DATA FLOW                                   │
 │                                                                         │
 │  Camera captures video frame                                            │
 │         │                                                               │
 │         ▼                                                               │
 │  AI detects all chickens in the frame                                   │
 │  └─ Draws a box around each chicken                                     │
 │         │                                                               │
 │         ▼                                                               │
 │  Each chicken is assigned a temporary track ID                          │
 │  └─ This keeps track of "Chicken A" across multiple frames              │
 │         │                                                               │
 │         ▼                                                               │
 │  Each chicken is identified by our Re-ID model                          │
 │  └─ "This is Chicken #17 — Raj's White Leghorn"                         │
 │         │                                                               │
 │         ▼                                                               │
 │  Health score is calculated for this chicken                            │
 │  └─ Based on movement, posture, distance from flock, etc.               │
 │         │                                                               │
 │         ▼                                                               │
 │  Results are saved to the database                                      │
 │  └─ Time, location, chicken ID, health score, snapshot image             │
 │         │                                                               │
 │         ▼                                                               │
 │  Dashboard updates in real time                                         │
 │  └─ You see the live video with boxes + names + health status            │
 │                                                                         │
 │  Total time: ~100-200 milliseconds per frame                            │
 └─────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Architecture Layers

### 3.1 Camera Layer

The system connects to **IP cameras** already installed in the field. These cameras typically connect to an **NVR (Network Video Recorder)** — a dedicated device that records 24/7 video to hard drives.

**What is an NVR?**
An NVR is the central hub for your security camera system already deployed on-site. It:
- Records video from all cameras continuously to internal hard drives
- Manages camera settings (resolution, frame rate, network config)
- Provides its own basic playback and monitoring interface
- Acts as the single management point for the camera network

**How our system connects alongside the NVR:**

Our AI server does **not** replace the NVR. It connects alongside it, reading the same live video streams without interfering with recording:

```
 ┌──────────────────────────────────────────────────────────┐
 │                   FIELD DEPLOYMENT                        │
 │                                                          │
 │  ┌─────────────────┐                                     │
 │  │   NVR            │  Records 24/7 from all cameras     │
 │  │   (Already       │  Stores to HDD, manages configs    │
 │  │   Deployed)      │  Provides playback UI              │
 │  └─────────────────┘                                     │
 │                                                          │
 │  Camera 1 ──RTSP──┬──────► NVR (24/7 recording)          │
 │  Camera 2 ──RTSP──┤                                       │
 │  Camera 3 ──RTSP──┼──────► Our AI Server (AI analysis)   │
 │  ...              │      (reads same RTSP streams,       │
 │  Camera 20 ──RTSP─┘       no interference)               │
 │                                                          │
 │  Our server grabs 5-10 frames per second for AI.         │
 │  The NVR continues recording 24/7 — unchanged.           │
 └──────────────────────────────────────────────────────────┘
```

**Two ways to connect:**

| Option | How it works | Best for |
|---|---|---|
| **Connect directly to cameras** | Our server reads RTSP from each camera's IP on the same network as the NVR. Zero load on NVR. | Most setups — keeps NVR isolated, no config changes needed |
| **Connect via NVR stream relay** | Many NVRs (Hikvision, Dahua, Uniview) can re-stream camera feeds via their own RTSP port. Single connection point. | When cameras are on a separate VLAN or firewall rules prevent direct access |

**Configuration per camera (set once in the dashboard):**
- RTSP URL (the network address of the camera or NVR relay)
- Location name (e.g., "Pen A", "West Wing")
- Frame rate (how many frames per second to process)
- Region of Interest (optional — crop to specific area)

**Key points:**
- No changes needed to existing camera wiring or NVR configuration
- Cameras connect over your local network (no internet required)
- Our system is **read-only** on the video streams — zero risk of interference
- If a camera disconnects, the system auto-reconnects and alerts you

---

### 3.2 Video Processing Layer

This is the **engine room.** The system uses **Frigate NVR** as the video processing backbone. Frigate handles all RTSP ingestion, motion detection, object detection (bird), recording, and HLS streaming via go2rtc. Our backend subscribes to Frigate's MQTT events to trigger health classification and MCMT re-identification on detected birds.

```
 ┌──────────────────────────────────────────────────────────────────┐
 │                    PROCESSING LAYER                               │
 │                                                                   │
 │  ┌───────────────────────────────────────────────────────────┐   │
 │  │  FRIGATE 0.17                                              │   │
 │  │  ───────────                                               │   │
 │  │  ● Ingests RTSP from every camera                          │   │
 │  │  ● Motion detection → triggers bird detection              │   │
 │  │  ● Built-in detector (OpenVINO/TensorRT/CPU)               │   │
 │  │  ● Records video to /media/frigate                         │   │
 │  │  ● go2rtc provides HLS + WebRTC streaming                  │   │
 │  │  ● Publishes events to Mosquitto (MQTT)                    │   │
 │  │  ● REST API at :5000 for stats, snapshots, config          │   │
 │  └───────────────────────────────────────────────────────────┘   │
 │                            │                                      │
 │              MQTT event: frigate/<cam>/events/new                 │
 │                            ▼                                      │
 │  ┌───────────────────────────────────────────────────────────┐   │
 │  │  BACKEND FRIGATE SUBSCRIBER (app.frigate.subscriber)       │   │
 │  │  ─────────────────────────────────────────────             │   │
 │  │                                                             │   │
 │  │  _handle_message(topic, payload)                            │   │
 │  │    ├─ Parse JSON from MQTT payload                          │   │
 │  │    ├─ Filter: only "bird" label events                      │   │
 │  │    ├─ Extract bbox, confidence, snapshot info               │   │
 │  │    ├─ _resolve_farm_id(camera_name) → DB lookup             │   │
 │  │    └─ _queue_health_check(camera, event)                    │   │
 │  │                                                             │   │
 │  │  _health_worker (background asyncio task)                   │   │
 │  │    ├─ Download snapshot from Frigate API                    │   │
 │  │    ├─ Crop bbox region from snapshot                        │   │
 │  │    ├─ Run MCMT tracker (MiewID + FAISS) → global_id         │   │
 │  │    ├─ Run HealthClassifier (best.pt) → health class         │   │
 │  │    ├─ Store to InfluxDB (detections + health measurements)  │   │
 │  │    └─ Broadcast via WebSocket (detections + health events)  │   │
 │  └───────────────────────────────────────────────────────────┘   │
 │                                                                   │
 │  ┌───────────────────────────────────────────────────────────┐   │
 │  │  go2rtc HLS STREAMING                                      │   │
 │  │  ─────────────────                                         │   │
 │  │  ● Frigate embeds go2rtc for sub-second HLS streaming      │   │
 │  │  ● Frontend plays HLS via hls.js                           │   │
 │  │  ● Frontend nginx proxies /api/frigate/hls/ → frigate:1984 │   │
 │  │  ● ~2-3 second latency (HLS)                               │   │
 │  └───────────────────────────────────────────────────────────┘   │
 └──────────────────────────────────────────────────────────────────┘
```

**Key differences from the previous architecture:**
- **Frigate replaces MediaMTX** for RTSP ingestion and HLS streaming
- **Frigate replaces the custom detection worker** — it handles motion detection and bird detection natively
- **No more round-robin polling** — Frigate continuously processes all camera streams in parallel
- **Event-driven** — health classification and MCMT run only when Frigate detects a bird, not on every frame
- **Recording built in** — Frigate records 24/7 footage with event-based clip generation

---

### 3.3 AI Inference Pipeline

The system uses a **two-stage pipeline** combining Frigate's built-in detection with our custom health and ReID models:

```
 ┌───────────────────────────────────────────────────────────────┐
 │                    AI INFERENCE PIPELINE                       │
 │                                                               │
 │  ┌────────────────────────────────────────────────────────┐   │
 │  │  STAGE 1: FRIGATE DETECTION (motion-triggered)          │   │
 │  │  ───────────────────────────────                       │   │
 │  │  ● Frigate detects motion in the camera stream          │   │
 │  │  ● Runs object detector (OpenVINO / TensorRT / CPU)     │   │
 │  │  ● Labels objects: "bird", "person", "vehicle" etc.     │   │
 │  │  ● Publishes MQTT event: frigate/<cam>/events/new       │   │
 │  │                                                         │   │
 │  │  Output per event: {label:"bird", bbox:[x1,y1,x2,y2],  │   │
 │  │                     confidence, snapshot available}      │   │
 │  └────────────────────────────────────────────────────────┘   │
 │                           │                                    │
 │              MQTT subscriber filters for "bird"                │
 │                           ▼                                    │
 │  ┌────────────────────────────────────────────────────────┐   │
 │  │  STAGE 2: CUSTOM HEALTH + REID (on Frigate snapshot)    │   │
 │  │  ──────────────────────────────────────                 │   │
 │  │                                                         │   │
 │  │  When a bird event arrives:                             │   │
 │  │                                                         │   │
 │  │  1. Download snapshot from Frigate API                   │   │
 │  │     GET /api/events/{id}/snapshot.jpg                    │   │
 │  │                                                         │   │
 │  │  2. Run MCMT ReID (MiewID + FAISS gallery)              │   │
 │  │     → Assigns global_id (cross-camera identity)         │   │
 │  │     → Uses bbox crop of the detected bird               │   │
 │  │                                                         │   │
 │  │  3. Run HealthClassifier (best.pt)                      │   │
 │  │     → 32-class health classification                    │   │
 │  │     → Returns health labels per detected chicken        │   │
 │  │                                                         │   │
 │  │  4. Store to InfluxDB                                   │   │
 │  │     → Measurement: detections (with global_id tag)      │   │
 │  │     → Measurement: health (with health_class tag)       │   │
 │  │                                                         │   │
 │  │  5. Broadcast via WebSocket                             │   │
 │  │     → "detection" event (type, bbox, global_id)         │   │
 │  │     → "health" event (health_results, global_id)        │   │
 │  └────────────────────────────────────────────────────────┘   │
 │                                                               │
 │  Models loaded once at startup, reused for every event.       │
 │  Only runs when Frigate detects a bird — no idle polling.     │
 └───────────────────────────────────────────────────────────────┘
```

**Why this two-stage approach?**
- Frigate handles the computationally expensive continuous video processing (24/7 motion + object detection)
- Our custom health + ReID models run only when needed (on detected bird events)
- No need for a separate counting model — Frigate's detector handles bird detection
- MCMT ReID enables cross-camera identity tracking (same chicken seen by different cameras)
- Health classification runs on high-quality snapshot crops instead of raw frames

---

### 3.4 Health Analysis Engine

The system uses the **health model (best.pt)** to directly classify health status from each detected chicken in the frame. This fine-tuned YOLO model was trained on labeled poultry health data and outputs health class labels (e.g., "healthy", "unhealthy") per detection.

```
 ┌──────────────────────────────────────────────────────────────┐
 │                    HEALTH ANALYSIS                            │
 │                                                              │
 │  For each captured frame, the health model runs directly      │
 │  on the full image and returns health-classified detections: │
 │                                                              │
 │  ┌──────────────────────────────────────────────────────┐    │
 │  │  HEALTH MODEL (best.pt)                             │    │
 │  │                                                      │    │
 │  │  ● YOLO11m fine-tuned on chicken health data        │    │
 │  │  ● Trained on ~32 classes of health/disease states   │    │
 │  │  ● Returns bounding boxes with health class labels  │    │
 │  │  ● Runs on the same frame as counting model         │    │
 │  │                                                      │    │
 │  │  Output example:                                     │    │
 │  │  ┌──────────────┬───────────┬───────────┐           │    │
 │  │  │ Bounding Box │ Class     │ Confidence│           │    │
 │  │  ├──────────────┼───────────┼───────────┤           │    │
 │  │  │ x:120,y:80.. │ healthy   │ 0.92      │           │    │
 │  │  │ x:200,y:50.. │ unhealthy │ 0.87      │           │    │
 │  │  │ x:300,y:100. │ healthy   │ 0.95      │           │    │
 │  │  └──────────────┴───────────┴───────────┘           │    │
 │  │                                                      │    │
 │  │  Results are published as "health" WebSocket events   │    │
 │  │  and stored in InfluxDB (measurement: health).        │    │
 │  └──────────────────────────────────────────────────────┘    │
 │                                                              │
 │  Health classifications are per-snapshot (not per-second).   │
 │  Each camera is analyzed every ~51 seconds (16 cams, 3s     │
 │  interval). This granularity is sufficient for detecting     │
 │  health conditions, which develop over minutes to hours.     │
 └──────────────────────────────────────────────────────────────┘
```

---

### 3.5 Backend API Layer

The backend is the **communication hub** — it connects the AI pipeline, the database, and the dashboard.

```
 ┌───────────────────────────────────────────────────────────────┐
 │                    BACKEND (FastAPI)                           │
 │                                                               │
 │  Receives requests from the dashboard and sends data back.    │
 │  Also manages WebSocket connections for real-time updates.    │
 │                                                               │
 │  ┌─────────────────────────────────────────────────────────┐  │
 │  │  What the backend does:                                 │  │
 │  │                                                         │  │
  │  │  ● Stores chicken information (names, IDs, breeds)      │  │
  │  │  ● Manages camera configurations                        │  │
  │  │  ● Serves detection history to the dashboard            │  │
  │  │  ● Pushes real-time alerts via WebSocket                │  │
  │  │  ● Handles user login and permissions                   │  │
  │  │  ● Aggregates statistics for analytics                  │  │
   │  │  ● Evaluates alert rules on every detection             │  │
   │  │  ● Serves environment telemetry data (IoT-ready)       │  │
   │  │  ● Manages farms (CRUD) and farm-level scoping        │  │
   │  │  ● Supports user impersonation for debugging           │  │
   │  │  ● Filters all data by farm_id via X-Farm-ID header   │  │
   │  └─────────────────────────────────────────────────────────┘  │
 │                                                               │
 │  Communication methods:                                       │
 │  ┌──────────────┐  ┌────────────────────────────────────┐     │
 │  │  REST API    │  │  WebSocket (real-time)             │     │
 │  │  ─────────   │  │  ─────────                         │     │
 │  │  Request →   │  │  Dashboard connects & stays open   │     │
 │  │  ← Response  │  │  Server pushes data as it happens  │     │
 │  │  For: CRUD,  │  │  For: Live detections, alerts      │     │
 │  │  queries     │  │  video overlays                    │     │
 │  └──────────────┘  └────────────────────────────────────┘     │
 │                                                               │
 └───────────────────────────────────────────────────────────────┘
```

---

### 3.6 Frontend Dashboard

The dashboard is a **web application** accessible from any browser — computer, tablet, or phone.

```
 ┌───────────────────────────────────────────────────────────────┐
 │                    FRONTEND DASHBOARD                          │
 │                                                               │
 │  Built with: React + TypeScript + Material UI                 │
 │  Runs in: Any modern web browser                              │
 │                                                               │
 │  ┌─────────────────────────────────────────────────────────┐  │
 │  │  MAIN PAGES:                                            │  │
 │  │                                                         │  │
 │  │  ┌──────────────────────────────────────────────────┐   │  │
 │  │  │ DASHBOARD (Home)                                 │   │  │
 │  │  │                                                 │   │  │
  │  │  │  Total Chickens: 50   Avg Health: 87%           │   │  │
  │  │  │  Cameras Online: 8/8  Active Alerts: 2          │   │  │
  │  │  │                                                 │   │  │
  │  │  │  Stats are derived from real data:               │   │  │
  │  │  │  ● Alerts = offline camera count                │   │  │
  │  │  │  ● Health = weighted composite (cameras,        │   │  │
  │  │  │    alerts, detection activity)                  │   │  │
  │  │  │  ● System badge / banner change with alert      │   │  │
  │  │  │    level (secure / attention / critical)        │   │  │
  │  │  │  ● Activity timeline driven by WebSocket        │   │  │
  │  │  │    events (detection, alert, camera status)     │   │  │
  │  │  │  ● Environment telemetry: API-ready endpoint    │   │  │
  │  │  │    with simulated fallback until IoT sensors    │   │  │
  │  │  │    are connected                                │   │  │
  │  │  │  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐           │   │  │
 │  │  │  │Cam 1 │ │Cam 2 │ │Cam 3 │ │Cam 4 │           │   │  │
 │  │  │  │Live  │ │Live  │ │Live  │ │Live  │           │   │  │
 │  │  │  └──────┘ └──────┘ └──────┘ └──────┘           │   │  │
 │  │  └──────────────────────────────────────────────────┘   │  │
 │  │                                                         │  │
 │  │  ┌──────────────────────────────────────────────────┐   │  │
 │  │  │ LIVE FEED                                        │   │  │
 │  │  │                                                 │   │  │
 │  │  │  See all cameras in a grid layout                │   │  │
 │  │  │  Each camera shows live video with:              │   │  │
 │  │  │  ● Bounding boxes around each chicken            │   │  │
 │  │  │  ● Chicken ID + name on each box                 │   │  │
 │  │  │  ● Health score color (green/yellow/red)         │   │  │
 │  │  │  ● Click any chicken to see full details         │   │  │
 │  │  └──────────────────────────────────────────────────┘   │  │
 │  │                                                         │  │
 │  │  ┌──────────────────────────────────────────────────┐   │  │
 │  │  │ CHICKENS                                         │   │  │
 │  │  │                                                 │   │  │
 │  │  │  Grid of all 50 chickens with:                   │   │  │
 │  │  │  ● Name, ID, breed, photo                       │   │  │
 │  │  │  ● Current health score (colored gauge)          │   │  │
 │  │  │  ● Status (active / monitoring / alert)          │   │  │
 │  │  │  ● Last seen location and time                   │   │  │
 │  │  │  ● Click → Full detail panel                     │   │  │
 │  │  │    ● Activity chart (last 24h)                   │   │  │
 │  │  │    ● Health trend over time                      │   │  │
 │  │  │    ● Detection timeline                          │   │  │
 │  │  │    ● Alert history                               │   │  │
 │  │  └──────────────────────────────────────────────────┘   │  │
 │  │                                                         │  │
 │  │  ┌──────────────────────────────────────────────────┐   │  │
 │  │  │ ANALYTICS & REPORTS                              │   │  │
 │  │  │                                                 │   │  │
 │  │  │  ● Health trends over 7/30/90 days               │   │  │
 │  │  │  ● Detection heatmap (when/where are chickens)   │   │  │
 │  │  │  ● Camera activity comparison                    │   │  │
 │  │  │  ● Alert breakdown by type                       │   │  │
 │  │  │  ● Export reports to CSV/PDF                     │   │  │
 │  │  └──────────────────────────────────────────────────┘   │  │
 │  │                                                         │  │
 │  │  ┌──────────────────────────────────────────────────┐   │  │
 │  │  │ ALERTS                                           │   │  │
 │  │  │                                                 │   │  │
 │  │  │  Real-time alert feed as notifications           │   │  │
 │  │  │  Alert list with filters (type, severity, date)  │   │  │
 │  │  │  Click to view context (which chicken, what cam) │   │  │
 │  │  │  Mark alerts as resolved                         │   │  │
 │  │  │  Configure alert rules (thresholds)              │   │  │
 │  │  └──────────────────────────────────────────────────┘   │  │
 │  │                                                         │  │
 │  │  ┌──────────────────────────────────────────────────┐   │  │
 │  │  │ SETTINGS                                         │   │  │
 │  │  │                                                 │   │  │
 │  │  │  ● Add/remove cameras                           │   │  │
 │  │  │  ● Add/update chicken profiles                   │   │  │
 │  │  │  ● Manage user accounts and permissions          │   │  │
 │  │  │  ● Adjust detection thresholds                  │   │  │
 │  │  │  ● Configure health score weights               │   │  │
 │  │  └──────────────────────────────────────────────────┘   │  │
 │  └─────────────────────────────────────────────────────────┘  │
 └───────────────────────────────────────────────────────────────┘
```

---

### 3.7 Data Storage Layer

Data is stored in three specialized databases, each optimized for its purpose:

```
 ┌───────────────────────────────────────────────────────────────┐
 │                    DATA STORAGE LAYER                          │
 │                                                               │
 │  ┌─────────────────────────────────────────────────────────┐  │
 │  │  POSTGRESQL — Relational Data                           │  │
 │  │  ──────────                                              │  │
 │  │  Stores structured information that doesn't change      │  │
 │  │  often:                                                  │  │
 │  │  ● Chickens (name, ID, breed, birth date, status)       │  │
 │  │  ● Cameras (name, RTSP URL, location, config)           │  │
 │  │  ● Users (email, password, role)                        │  │
 │  │  ● Alerts (type, severity, message, resolved)           │  │
 │  │  ● Alert rules (thresholds, enabled status)             │  │
 │  │  ● Health score snapshots (periodic records)            │  │
 │  │  ● Detection events (partitioned by month)              │  │
 │  └─────────────────────────────────────────────────────────┘  │
 │                                                               │
 │  ┌─────────────────────────────────────────────────────────┐  │
 │  │  INFLUXDB — Time-Series Data                           │  │
 │  │  ─────────                                              │  │
 │  │  Optimized for storing millions of timestamped data     │  │
 │  │  points efficiently:                                    │  │
 │  │  ● Detection events (every time a chicken is seen)      │  │
 │  │  ● Health scores (recalculated per detection)           │  │
 │  │  ● Activity logs (speed, distance traveled per frame)   │  │
 │  │  ● IoT sensor readings (temp, humidity, ammonia)        │  │
 │  │                                                         │  │
 │  │  Automatically manages data retention:                  │  │
 │  │  ● Raw data: 30 days                                    │  │
 │  │  ● Aggregated (hourly): 1 year                          │  │
 │  │  ● Aggregated (daily): forever                          │  │
 │  └─────────────────────────────────────────────────────────┘  │
 │                                                               │
 │  ┌─────────────────────────────────────────────────────────┐  │
 │  │  REDIS — Cache & Real-Time                              │  │
 │  │  ───────                                                 │  │
 │  │  Super-fast in-memory storage for temporary data:        │  │
 │  │  ● Frame buffer (recent frames waiting to be processed)  │  │
 │  │  ● Active track states (where each chicken is right now) │  │
 │  │  ● Celery task queue (schedules processing work)         │  │
 │  │  ● WebSocket pub/sub (pushes updates to dashboard)       │  │
 │  │  ● User sessions                                         │  │
 │  └─────────────────────────────────────────────────────────┘  │
 │                                                               │
 │  ┌─────────────────────────────────────────────────────────┐  │
 │  │  MINIO / S3 — Object Storage                            │  │
 │  │  ───────────                                             │  │
 │  │  Stores large files:                                     │  │
 │  │  ● Snapshots of detected chickens (for review)           │  │
 │  │  ● Archived video clips when alerts trigger              │  │
 │  │  ● Model weight files (versioned for rollback)           │  │
 │  └─────────────────────────────────────────────────────────┘  │
 └───────────────────────────────────────────────────────────────┘
```

---

## 4. How Chickens Are Identified

Each chicken in your farm is assigned a **unique ID** (0–49). The AI model was trained on photos of each chicken to recognize its **visual appearance** (color, pattern, comb shape, size, etc.).

```
 ┌───────────────────────────────────────────────────────────────┐
 │                    RE-IDENTIFICATION PROCESS                   │
 │                                                               │
 │  Step 1: The chicken detector finds a chicken in the frame    │
 │  Step 2: The chicken image is cropped from the scene          │
 │  Step 3: The re-ID model compares it against all 50 known     │
 │          chickens and picks the best match                    │
 │  Step 4: Result: "This is Chicken #17 with 92% confidence"    │
 │                                                               │
 │  ┌─────────────────────────────────────────────────────────┐  │
 │  │  Example confidence output:                             │  │
 │  │                                                         │  │
 │  │  Chicken #17: 92%  ← Best match, accepted               │  │
 │  │  Chicken #33:  4%                                       │  │
 │  │  Chicken #05:  2%                                       │  │
 │  │  Chicken #41:  1%                                       │  │
 │  │  ...others:   <1%                                       │  │
 │  │                                                         │  │
 │  │  If no chicken matches above 60%, flagged as            │  │
 │  │  "Unidentified" — you can name it later.                │  │
 │  └─────────────────────────────────────────────────────────┘  │
 │                                                               │
 │  Can you add more chickens?                                   │
 │  Yes! We would collect photos of the new chicken, add it      │
 │  to the training dataset, and retrain the model.              │
 │                                                               │
 │  Current model: 50 chickens                                   │
 │  Future: 100, 500, or more — model can be scaled up.          │
 └───────────────────────────────────────────────────────────────┘
```

---

## 5. Health Scoring System

The health score is a **0–100 composite** updated every time a chicken is detected.

```
 ┌───────────────────────────────────────────────────────────────┐
 │                    HEALTH SCORE CALCULATION                    │
 │                                                               │
 │  Formula:                                                     │
 │                                                               │
 │  HEALTH = (Activity × 0.40)                                   │
 │          + (Posture  × 0.25)                                  │
 │          + (Social   × 0.15)                                  │
 │          + (Sensor   × 0.20)                                  │
 │                                                               │
 │  Example:                                                     │
 │  ┌────────────┬──────┬───────┬────────┐                      │
 │  │ Component  │ Raw  │ Score │ Weight │                      │
 │  ├────────────┼──────┼───────┼────────┤                      │
 │  │ Activity   │ Good │  85   │ × 40%  │ = 34.0               │
 │  │ Posture    │ Fair │  60   │ × 25%  │ = 15.0               │
 │  │ Social     │ Good │  90   │ × 15%  │ = 13.5               │
 │  │ Sensor     │ Good │  80   │ × 20%  │ = 16.0               │
 │  ├────────────┼──────┼───────┼────────┼────────┤             │
 │  │ FINAL      │      │       │        │  78.5  │             │
 │  └────────────┴──────┴───────┴────────┴────────┘             │
 │                                                               │
 │  ┌───────────────────────────────────────────────────────┐    │
 │  │  Color Code:   ● 80-100: Healthy  (Green)            │    │
 │  │                ● 50-79:  Monitor  (Yellow)           │    │
 │  │                ● 30-49:  Warning  (Orange)           │    │
 │  │                ● 0-29:   Critical (Red)              │    │
 │  └───────────────────────────────────────────────────────┘    │
 │                                                               │
 │  The weights can be adjusted in Settings if you want to       │
 │  prioritize different factors.                                │
 └───────────────────────────────────────────────────────────────┘
```

---

## 6. Alert System

The system continuously monitors all chickens and triggers alerts when something is wrong.

```
 ┌───────────────────────────────────────────────────────────────┐
 │                    ALERT SYSTEM                                │
 │                                                               │
 │  When does an alert fire?                                     │
 │                                                               │
 │  ┌─────────────────────────────────────────────────────────┐  │
 │  │  INACTIVITY ALERT                                       │  │
 │  │  Chicken hasn't moved in 30+ minutes                    │  │
 │  │  → Could be sick, injured, or trapped                   │  │
 │  │  → Severity: Warning (30min) / Critical (60min)         │  │
 │  └─────────────────────────────────────────────────────────┘  │
 │                                                               │
 │  ┌─────────────────────────────────────────────────────────┐  │
 │  │  ISOLATION ALERT                                        │  │
 │  │  Chicken is far from the flock for 15+ minutes          │  │
 │  │  → Could be sick or injured                             │  │
 │  │  → Severity: Warning                                    │  │
 │  └─────────────────────────────────────────────────────────┘  │
 │                                                               │
 │  ┌─────────────────────────────────────────────────────────┐  │
 │  │  HEALTH DROP ALERT                                      │  │
 │  │  Health score dropped 30%+ in the last 24 hours         │  │
 │  │  → Sudden deterioration                                 │  │
 │  │  → Severity: Warning                                    │  │
 │  └─────────────────────────────────────────────────────────┘  │
 │                                                               │
 │  ┌─────────────────────────────────────────────────────────┐  │
 │  │  HEALTH CRITICAL                                        │  │
 │  │  Health score below 30                                   │  │
 │  │  → Chicken needs immediate attention                    │  │
 │  │  → Severity: Critical                                   │  │
 │  └─────────────────────────────────────────────────────────┘  │
 │                                                               │
 │  ┌─────────────────────────────────────────────────────────┐  │
 │  │  TEMPERATURE / ENVIRONMENT ALERT                        │  │
 │  │  Coop temperature above 35°C for 30+ minutes            │  │
 │  │  or humidity outside safe range                          │  │
 │  │  → Environmental stress affecting all chickens          │  │
 │  │  → Severity: Warning / Critical                         │  │
 │  └─────────────────────────────────────────────────────────┘  │
 │                                                               │
 │  ┌─────────────────────────────────────────────────────────┐  │
 │  │  MISSING CHICKEN ALERT                                  │  │
 │  │  A specific chicken hasn't been seen in 6+ hours        │  │
 │  │  by any camera (and cameras cover its zone)             │  │
 │  │  → Could be trapped, escaped, or deceased               │  │
 │  │  → Severity: Critical                                   │  │
 │  └─────────────────────────────────────────────────────────┘  │
 │                                                               │
 │  All alert thresholds are configurable in the Settings page.  │
 │  Alerts appear in real-time on the dashboard and are logged   │
 │  for review.                                                  │
 └───────────────────────────────────────────────────────────────┘
```

---

## 7. Database Design

### 7.1 PostgreSQL (Relational Data)

```
 ┌───────────────────────────────────────────────────────────────┐
 │                    DATABASE TABLES                             │
 │                                                               │
 │  farms ────────┬─── chickens ──────────┬─── cameras           │
 │  ┌─────────┐   │    ┌──────────────┐   │    ┌────────┐       │
 │  │ id      │   │    │ id           │   │    │ id     │       │
 │  │ name    │◄──┤    │ chicken_id   │   │    │ name   │       │
 │  │ slug    │   │    │ farm_id ─────┼───┤    │ farm_id│       │
 │  │ location│   │    │ breed        │   │    │ rtsp   │       │
 │  │ settings│   │    │ status       │   │    │ ...    │       │
 │  │ active  │   │    │ ...          │   │    └────────┘       │
 │  └─────────┘   │    └──────────────┘   │                      │
 │                │                        │                      │
 │                │    users               │    alert_rules       │
 │                │    ┌──────────────┐    │    ┌──────────────┐  │
 │                │    │ id           │    │    │ id           │  │
 │                │    │ email        │    │    │ farm_id ─────┼──┤
 │                │    │ farm_id ─────┼────┤    │ name         │  │
 │                │    │ role_id      │    │    │ ...          │  │
 │                │    │ ...          │    │    └──────────────┘  │
 │                │    └──────────────┘    │                      │
 │                │                        │                      │
 │                │    alerts ─────────────┘                      │
 │                │    ┌──────────────┐                           │
 │                └────│ farm_id      │                           │
 │                     │ chicken_id   │                           │
 │                     │ type         │                           │
 │                     │ ...          │                           │
 │                     └──────────────┘                           │
 │                                                               │
 │  Each data table (chickens, cameras, alerts, alert_rules,     │
 │  users) has a farm_id FK → farms. Every query filters by      │
 │  farm_id via the get_farm_id() dependency (from JWT or header).│
 └───────────────────────────────────────────────────────────────┘
```

**Key design decisions:**
- `farm_id` is NOT NULL on all data tables — every record belongs to a farm
- `farm_id` is NULLABLE on `users` — NULL means super admin (accesses all farms)
- Chicken IDs are unique within a farm via composite unique `(farm_id, chicken_id)`
- Super admin uses `X-Farm-ID` header (set by frontend axios interceptor) to scope their view

### 7.2 InfluxDB (Time-Series Data)

| Data Type | What's Stored | Retention | Farm Isolation |
|---|---|---|---|---|
| **Detections** | Every time a chicken is seen: chicken ID, camera, location in frame, confidence | 30 days raw, 1 year hourly avg | `farm_id` tag on every point |
| **Health Scores** | Per-chicken health score every time it's calculated | 30 days raw, forever daily avg | `farm_id` tag on every point |
| **Activity Logs** | Movement speed, distance traveled between frames | 30 days raw, 1 year hourly avg | `farm_id` tag on every point |
| **Sensor Readings** | Temperature, humidity, ammonia per camera location | 30 days raw, forever hourly avg | `farm_id` tag on every point |

---

## 8. API Endpoints

The backend provides the following communication channels for the dashboard:

```
 ┌───────────────────────────────────────────────────────────────┐
 │                    API ENDPOINTS                               │
 │                                                               │
 │  All REST endpoints are prefixed with /v1                     │
 │  (e.g. /v1/chickens, /v1/cameras).                            │
 │                                                               │
 │  Auth:                                                         │
 │    POST   /auth/register            Create account             │
 │    POST   /auth/login               Login (returns JWT)       │
 │    POST   /auth/refresh             Refresh access token       │
 │    POST   /auth/logout              Invalidate session         │
 │    GET    /auth/me                  Current user profile       │
 │    POST   /auth/change-password     Update password            │
 │    GET    /auth/users               List all users (admin)    │
 │    POST   /auth/impersonate/{id}    Impersonate user (super)  │
 │                                                               │
 │  Cameras:                                                      │
 │    GET    /cameras              List all cameras              │
 │    GET    /cameras/{id}         Get camera detail             │
 │    POST   /cameras              Add camera                    │
 │    PUT    /cameras/{id}         Update camera                 │
 │    DELETE /cameras/{id}         Remove camera                 │
 │    POST   /cameras/scan         Start ONVIF network scan     │
 │    GET    /cameras/scan/status  Scan progress                 │
 │    GET    /cameras/scan/results Discovered devices            │
 │                                                               │
 │  Chickens:                                                     │
 │    GET    /chickens             List registered chickens      │
 │    GET    /chickens/detected    Auto-detected (from InfluxDB) │
 │    GET    /chickens/{id}        Get chicken detail            │
 │    POST   /chickens             Register a chicken            │
 │    PUT    /chickens/{id}        Update chicken                │
 │    DELETE /chickens/{id}        Remove chicken                │
 │                                                               │
 │  Detection (control + query):                                  │
 │    POST   /cameras/{id}/detection/start    Enable detection   │
 │    POST   /cameras/{id}/detection/stop     Disable detection  │
 │    GET    /cameras/{id}/detection/status    Running/idle      │
 │    GET    /cameras/{id}/detection/stats     Aggregated stats  │
 │    GET    /cameras/{id}/detection/history   Time-series data  │
 │    GET    /cameras/{id}/detection/summary   Per-camera summary│
 │    GET    /detection/global/history         All-camera view   │
 │                                                               │
 │  Farms:                                                        │
 │    GET    /farms                 List all farms (super)        │
 │    POST   /farms                Create farm (super)           │
 │    GET    /farms/{id}           Get farm detail               │
 │    PUT    /farms/{id}           Update farm (super)           │
 │    DELETE /farms/{id}           Delete farm (super)           │
 │                                                               │
 │  Environment:  (stub — returns no_data until IoT sensors)    │
 │    GET    /environment           Current readings             │
 │    GET    /environment/history   Time-series                  │
 │                                                               │
 │  Root:                                                         │
 │    GET    /health               Server health check           │
 │                                                               │
 │  WebSocket (real-time push):                                  │
 │    WS /ws   Auth via ?token=, subscribes to channels:         │
 │             global, detections, alerts, camera_status         │
 │             Farm-scoped channels: farm_{id}/detections,       │
 │             farm_{id}/alerts, farm_{id}/camera_status        │
 └───────────────────────────────────────────────────────────────┘
```

---

## 9. Frontend Screens

```
 ┌───────────────────────────────────────────────────────────────┐
 │                    DASHBOARD PAGES                             │
 │                                                               │
 │  ┌─────────────────────────────────────────────────────────┐  │
 │  │  DASHBOARD  (/dashboard)                                │  │
 │  │  Landing page showing overall farm status at a glance   │  │
 │  │                                                         │  │
 │  │  ┌─────────────┐ ┌─────────────┐ ┌──────────────┐     │  │
 │  │  │ 50 Chickens │ │ Avg Health  │ │ 8 Cameras    │     │  │
 │  │  │ Total       │ │ 87%         │ │ All Online   │     │  │
 │  │  └─────────────┘ └─────────────┘ └──────────────┘     │  │
 │  │  ┌─────────────┐ ┌────────────────────────────────┐   │  │
 │  │  │ 2 Active    │ │ Health Distribution Chart     │   │  │
 │  │  │ Alerts      │ │ [Healthy: 42] [Monitor: 6]    │   │  │
 │  │  └─────────────┘ │ [Warning: 2] [Critical: 0]    │   │  │
 │  │                  └────────────────────────────────┘   │  │
 │  │  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐                 │  │
 │  │  │Cam 1 │ │Cam 2 │ │Cam 3 │ │Cam 4 │ (mini live)    │  │
 │  │  └──────┘ └──────┘ └──────┘ └──────┘                 │  │
 │  └─────────────────────────────────────────────────────────┘  │
 │                                                               │
 │  ┌─────────────────────────────────────────────────────────┐  │
 │  │  LIVE FEED  (/live)                                     │  │
 │  │  Full-screen camera grid with real-time AI overlays     │  │
 │  │                                                         │  │
 │  │  ┌─────────────────────┐  ┌─────────────────────┐      │  │
 │  │  │ 🎥 Pen A - Cam 1    │  │ 🎥 Pen B - Cam 2    │      │  │
 │  │  │ ┌─────────────────┐ │  │ ┌─────────────────┐ │      │  │
 │  │  │ │  🐔 #17 (Raj)   │ │  │ │  🐔 #33 (Maya)  │ │      │  │
 │  │  │ │  ████████████   │ │  │ │    ████████████  │ │      │  │
 │  │  │ │  🐔 #05 (Snow)  │ │  │ │  🐔 #41 (Kali)  │ │      │  │
 │  │  │ └─────────────────┘ │  │ └─────────────────┘ │      │  │
 │  │  │ 4 chickens detected │  │ 3 chickens detected  │      │  │
 │  │  └─────────────────────┘  └─────────────────────┘      │  │
 │  └─────────────────────────────────────────────────────────┘  │
 │                                                               │
 │  ┌─────────────────────────────────────────────────────────┐  │
 │  │  CHICKENS  (/chickens)                                  │  │
 │  │  Browse all chickens with search, filter, and sort      │  │
 │  │                                                         │  │
 │  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐  │  │
 │  │  │ 🐔 #17   │ │ 🐔 #33   │ │ 🐔 #05   │ │ 🐔 #41   │  │  │
 │  │  │ Raj      │ │ Maya     │ │ Snow     │ │ Kali     │  │  │
 │  │  │ ● 92%    │ │ ● 78%    │ │ ● 45%    │ │ ● 88%    │  │  │
 │  │  │ White Leg│ │ RIR      │ │ Sussex   │ │ Wyandotte│  │  │
 │  │  │ Active   │ │ Active   │ │ ⚠️ Warn  │ │ Active   │  │  │
 │  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘  │  │
 │  └─────────────────────────────────────────────────────────┘  │
 │                                                               │
 │  ┌─────────────────────────────────────────────────────────┐  │
 │  │  CHICKEN DETAIL  (click on a chicken)                   │  │
 │  │                                                         │  │
 │  │  ┌────────────┐  Health Score: ● 78/100 (Monitor)      │  │
 │  │  │  🐔 Photo  │  Activity: ████████░░  82/100          │  │
 │  │  │  #17       │  Posture:  ██████░░░░  60/100          │  │
 │  │  │  "Raj"     │  Social:   █████████░  90/100          │  │
 │  │  └────────────┘  Sensor:   ████████░░  80/100          │  │
 │  │                                                         │  │
 │  │  Activity over 24h:  ▁▂▄▆█▇▅▃▂▁▁▂▃▅▇█▆▄▃▂▁          │  │
 │  │  Last seen: Pen A, Cam 1, 2 minutes ago                │  │
 │  │  Alerts: 2 (both resolved)                             │  │
 │  └─────────────────────────────────────────────────────────┘  │
 │                                                               │
 │  ┌─────────────────────────────────────────────────────────┐  │
 │  │  ANALYTICS  (/analytics)                                │  │
 │  │  Health trends, detection patterns, reports             │  │
 │  │                                                         │  │
 │  │  ┌──────────────────────────────────────────────────┐   │  │
 │  │  │  Avg Health Score (Last 30 Days)                 │   │  │
 │  │  │  ▁▂▃▄▅▆▇██▇▆▅▄▃▂▁▁▂▃▄▅▆▇██▇▆▅▄                │   │  │
 │  │  └──────────────────────────────────────────────────┘   │  │
 │  │  ┌────────────────┐ ┌────────────────────────────┐     │  │
 │  │  │ Detection by   │ │ Alert Breakdown            │     │  │
 │  │  │ Hour of Day    │ │ [Bar chart by type]        │     │  │
 │  │  │ [Heatmap]      │ └────────────────────────────┘     │  │
 │  │  └────────────────┘                                    │  │
 │  └─────────────────────────────────────────────────────────┘  │
 └───────────────────────────────────────────────────────────────┘
```

---

## 10. Technology Stack

```
 ┌───────────────────────────────────────────────────────────────┐
 │                    TECHNOLOGY STACK                            │
 │                                                               │
 │  ┌─────────────────────────────────────────────────────────┐  │
 │  │  FRONTEND (Web Dashboard)                               │  │
 │  │  ────────────────────────                                │  │
 │  │  ● React + TypeScript        — UI framework             │  │
 │  │  ● Vite                     — Build tool (fast)         │  │
 │  │  ● Material UI (MUI)        — Pre-built components      │  │
 │  │  ● Recharts                 — Charts & graphs           │  │
 │  │  ● HLS.js                   — Live video streaming      │  │
 │  │  ● Axios                    — API communication         │  │
 │  └─────────────────────────────────────────────────────────┘  │
 │                                                               │
 │  ┌─────────────────────────────────────────────────────────┐  │
 │  │  BACKEND (Server)                                       │  │
 │  │  ─────────────────                                       │  │
 │  │  ● Python 3.11               — Language                  │  │
 │  │  ● FastAPI                   — Web framework (async)    │  │
 │  │  ● Uvicorn                   — Server                    │  │
 │  │  ● SQLAlchemy                — Database ORM             │  │
 │  │  ● Alembic                   — Database migrations      │  │
 │  │  ● SlowAPI                   — Rate limiting            │  │
 │  │  ● Redis                     — Cache + task broker      │  │
 │  │  ● JWT                       — Authentication           │  │
 │  └─────────────────────────────────────────────────────────┘  │
 │                                                               │
 │  ┌─────────────────────────────────────────────────────────┐  │
 │  │  AI / ML                                                │  │
 │  │  ───────                                                │  │
 │  │  ● Ultralytics YOLO11m      — Counting model           │  │
 │  │  ● PyTorch                  — Deep learning framework   │  │
 │  │  ● ByteTrack                — Multi-object tracking     │  │
 │  │  ● OpenCV                   — Image processing          │  │
 │  │  ● TensorRT                 — Model optimization (Jetson)│  │
 │  └─────────────────────────────────────────────────────────┘  │
 │                                                               │
 │  ┌─────────────────────────────────────────────────────────┐  │
 │  │  NVR + STREAMING                                        │  │
 │  │  ───────────────                                        │  │
 │  │  ● Frigate 0.17             — NVR + object detection    │  │
 │  │  ● go2rtc                    — HLS/WebRTC streaming     │  │
 │  │  ● HLS.js                   — Browser video player      │  │
 │  │  ● Mosquitto (MQTT)         — Event bus for detections  │  │
 │  └─────────────────────────────────────────────────────────┘  │
 │                                                               │
 │  ┌─────────────────────────────────────────────────────────┐  │
 │  │  DATABASES                                              │  │
 │  │  ──────────                                              │  │
 │  │  ● PostgreSQL               — Relational data           │  │
 │  │  ● InfluxDB                 — Time-series data          │  │
 │  │  ● Redis                    — Cache + real-time         │  │
 │  │  ● MinIO (S3-compatible)    — File/object storage       │  │
 │  └─────────────────────────────────────────────────────────┘  │
 │                                                               │
 │  ┌─────────────────────────────────────────────────────────┐  │
 │  │  INFRASTRUCTURE                                         │  │
 │  │  ──────────────                                         │  │
 │  │  ● Docker + Docker Compose   — Containerization        │  │
 │  │  ● NVIDIA CUDA               — GPU acceleration         │  │
 │  │  ● Nginx                     — Reverse proxy + SSL     │
 │  ● Cloudflare Tunnel          — Internet exposure       │  │
 │  └─────────────────────────────────────────────────────────┘  │
 └───────────────────────────────────────────────────────────────┘
```

---

## 11. Deployment Architecture

The system runs as a set of **Docker containers** managed by Docker Compose. It can be deployed on a GPU server or a **Jetson Orin Nano** edge device.

### 11.1 Jetson Orin Nano (Recommended for Edge Deployment)

```
 ┌───────────────────────────────────────────────────────────────┐
 │              JETSON ORIN NANO (8 GB)                           │
 │                                                               │
 │  ┌─────────────────────────────────────────────────────────┐  │
 │  │  Docker Compose Stack                                   │  │
 │  │                                                         │  │
 │  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌────────┐ │  │
 │  │  │ nginx    │  │ FastAPI  │  │ Frigate  │  │ Redis  │ │  │
 │  │  │ (proxy)  │  │ Backend  │  │(NVR+det) │  │(cache) │ │  │
 │  │  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────────┘ │  │
 │  │       │              │              │                   │  │
 │  │       └──────────────┼──────────────┘                   │  │
 │  │                      │                                  │  │
 │  │  ┌──────────────────────────────────────────────────┐   │  │
 │  │  │  NVIDIA GPU (CUDA + Tensor Cores)                │   │  │
 │  │  │  ┌──────────────┐  ┌──────────────┐              │   │  │
 │  │  │  │ best.pt      │  │ Frigate      │              │   │  │
 │  │  │  │ (health)     │  │ (detector)   │              │   │  │
 │  │  │  │ PyTorch      │  │ OpenVINO/TRT │              │   │  │
 │  │  │  └──────────────┘  └──────────────┘              │   │  │
 │  │  └──────────────────────────────────────────────────┘   │  │
 │  └─────────────────────────────────────────────────────────┘  │
 │                                                               │
 │  ┌──────────────────────────────────────────────────────┐    │
 │  │  CAMERA NETWORK                                       │    │
 │  │                                                       │    │
 │  │  Camera 1 ──RTSP──┐                                   │    │
 │  │  Camera 2 ──RTSP──┤  Same local network               │    │
 │  │  ...              │  (Gigabit Ethernet)               │    │
 │  │  Camera 16 ──RTSP─┘                                   │    │
 │  └──────────────────────────────────────────────────────┘    │
 │                                                               │
 │  Internet access via Cloudflare Tunnel or Tailscale Funnel:   │
 │  ┌──────────────────────────────────────────────────────┐    │
 │  │  Cloudflare Tunnel → https://your-domain.com → nginx │    │
 │  └──────────────────────────────────────────────────────┘    │
 └───────────────────────────────────────────────────────────────┘
```

### 11.2 Deployment Options

| Platform | Hardware | GPU | RAM |
|---|---|---|---|
| **Jetson Orin Nano 8 GB** | Edge device | 1024 CUDA + TensorRT | 8 GB shared |
| **GPU Server** | PC (RTX 3060+) | Dedicated GPU | 16GB+ |

### 11.3 Setup

```bash
# Install Docker + NVIDIA runtime
sudo apt install docker.io nvidia-container-runtime
sudo systemctl enable --now docker

# Run
cp .env.example .env
# Edit .env with secure passwords
docker compose build
docker compose up -d

# Internet exposure
docker run cloudflare/cloudflared tunnel --no-autoupdate run --token YOUR_TOKEN
```

### 11.4 Container Stack

| Service | Image | Purpose |
|---|---|---|
| `postgres` | postgres:16 | Main database (cameras, users, config) |
| `influxdb` | influxdb:2.7 | Time-series detection data |
| `redis` | redis:7-alpine | Caching + rate limiting |
| `minio` | minio/minio | Object storage (snapshots) |
| `frigate` | ghcr.io/blakeblackshear/frigate:0.17 | NVR + motion/bird detection + HLS streaming |
| `mosquitto` | eclipse-mosquitto:2.0 | MQTT broker for Frigate events |
| `backend` | custom | FastAPI + HealthClassifier + MCMT ReID (GPU-enabled) |
| `frontend` | custom | nginx serving React dashboard |
| `cloudflared` | cloudflare/cloudflared | Optional: internet tunnel |

---

## 12. Implementation Roadmap

```
 ┌───────────────────────────────────────────────────────────────┐
 │                    IMPLEMENTATION ROADMAP                      │
 │                                                               │
 │  PHASE 1 — Foundation (2 weeks)                               │
 │  ┌─────────────────────────────────────────────────────────┐  │
 │  │  □ Set up backend project (FastAPI + database)          │  │
 │  │  □ Create database tables and migrations                │  │
 │  │  □ Build login and user management                      │  │
 │  │  □ Create Chicken and Camera management (CRUD)          │  │
 │  │  □ Set up camera RTSP frame grabber                     │  │
 │  │  □ Build basic dashboard layout with live video         │  │
 │  │  □ Deploy the backend and frontend skeleton             │  │
 │  └─────────────────────────────────────────────────────────┘  │
 │                                                               │
 │  PHASE 2 — AI Detection (2 weeks)                             │
 │  ┌─────────────────────────────────────────────────────────┐  │
 │  │  □ Train Stage 1 chicken detector (collect + label)     │  │
 │  │  □ Integrate existing 50-class re-ID model as Stage 2  │  │
 │  │  □ Implement ByteTrack for chicken tracking             │  │
 │  │  □ Build AI processing pipeline (Celery worker)         │  │
 │  │  □ Add detection overlay to live camera feed            │  │
 │  │  □ Push real-time detection data via WebSocket          │  │
 │  │  □ Show live bounding boxes with chicken IDs in UI     │  │
 │  └─────────────────────────────────────────────────────────┘  │
 │                                                               │
 │  PHASE 3 — Health Monitoring (2 weeks)                        │
 │  ┌─────────────────────────────────────────────────────────┐  │
 │  │  □ Implement health scoring engine                       │  │
 │  │  □ Build alert rule engine                               │  │
 │  │  □ Create health score + trend charts in UI             │  │
 │  │  □ Build alert list and notification system             │  │
 │  │  □ Add chicken detail panel (health + history)          │  │
 │  │  □ Integrate IoT sensor data (if available)              │  │
 │  │  □ Create alert configuration in Settings               │  │
 │  └─────────────────────────────────────────────────────────┘  │
 │                                                               │
 │  PHASE 4 — Analytics & Scale (2 weeks)                        │
 │  ┌─────────────────────────────────────────────────────────┐  │
 │  │  □ Build analytics page with date-range filters         │  │
 │  │  □ Create population and detection trend charts         │  │
 │  │  □ Add detection heatmap and camera comparison          │  │
 │  │  □ Build report export (CSV/PDF)                        │  │
 │  │  □ Performance optimization (model export, caching)     │  │
 │  │  □ Docker Compose finalization + deployment docs        │  │
 │  │  □ Final testing with 5-20 cameras                      │  │
 │  └─────────────────────────────────────────────────────────┘  │
 │                                                               │
 │  Total estimated time: 8 weeks                                │
 └───────────────────────────────────────────────────────────────┘
```

---

## 13. Edge Cases & How We Handle Them

| Scenario | How the System Handles It |
|---|---|
| **Camera disconnects** | Auto-reconnects every 10 seconds. Dashboard shows camera as "Offline". Alert sent if offline > 5 minutes. |
| **Chicken leaves frame** | ByteTrack tracker keeps the chicken's ID for 30 seconds after it leaves. If it returns, it gets the same ID. After 30s, the ID is released. |
| **New/unidentified chicken** | Stage 2 classifier returns low confidence (<60%). Chicken tagged as "Unidentified" in the UI. You can name it later and add to the model. |
| **Multiple chickens overlapping** | The detector still finds each chicken. ByteTrack handles occlusions by predicting position even when partially hidden. |
| **Night time / low light** | System can be configured to only process during set hours. Or use IR-capable cameras (most IP cameras have IR). |
| **All cameras go offline** | Dashboard shows clear "All Cameras Offline" state. Existing data remains accessible. Alerts are triggered. |
| **No chickens in frame** | Worker skips processing that frame (nothing to do). Dashboard shows "No chickens detected" per camera. |
| **Database grows large** | PostgreSQL partitions detection data by month. InfluxDB auto-expires old data. Old data can be archived. |
| **Power outage** | All services restart automatically when power returns (Docker restart policy). Processing resumes with no data loss. |
| **Wrong identification** | The model always reports confidence. Low-confidence IDs are shown with a "?" indicator in the UI. You can manually correct the ID. |
| **NVR goes offline** | NVR failure does not stop AI processing — our server reads cameras directly. If both NVR and cameras are unreachable, dashboard shows offline status. When NVR recovers, its recorded footage is unaffected. |

---

## Appendix — How the AI Model Works (Simplified)

For non-technical stakeholders:

> **Think of YOLO11m as a super-fast pattern matcher.**
> 
> During training, we showed the model thousands of photos of chickens. The model learned to recognize patterns — feather colors, comb shapes, body sizes, and health indicators.
> 
> When a new camera frame comes in:
> 1. The model scans the entire image in one pass
> 2. It identifies every chicken-shaped object and draws a box around each one
> 3. It counts how many chickens it found
> 4. A second model simultaneously classifies each chicken's health status
> 
> The entire process takes about **200 milliseconds per frame on a Jetson Orin Nano** — faster than a human blink.
---



> **Document Version:** 3.0  
> **Last Updated:** June 2026  
> **Prepared for:** Client Review
---

## 14. Security Architecture

### 14.1 Network Security
- **VLAN segmentation:** Cameras, NVR, GPU server, and office LAN on separate VLANs
- **Firewall rules:** GPU server can initiate RTSP connections; cameras cannot reach GPU server
- **Cloudflare Tunnel** for internet exposure (no open inbound ports)
- **WireGuard VPN** for remote admin access (alternative to Cloudflare)

### 14.2 Application Security
- **Cookie-based auth** (httpOnly, SameSite=Lax) — JWT stored in secure cookies, not localStorage
- **Role-based access control (RBAC):** Viewer, Operator, Admin, Super-admin — scoped by farm
- **Farm-level data isolation** — every API endpoint filters by `farm_id` from JWT or `X-Farm-ID` header
- **Impersonation tokens** — short-lived (15 min), scoped to target user's role/permissions; Authorization header takes priority over cookie
- **API rate limiting** (auth endpoints: 20/h register, 20/m refresh, 5/m change-pw)
- **CSP security headers** enforced by nginx (X-Frame-Options, X-Content-Type-Options, X-XSS-Protection)
- **Input validation** on all API endpoints (Pydantic models with strict mode)
- **SQL injection prevention** via parameterized queries (SQLAlchemy, InfluxDB `params=` API)

### 14.3 Data Security
- **At-rest encryption:** PostgreSQL (TDE), MinIO (SSE-S3), InfluxDB (encryption enabled)
- **In-transit encryption:** TLS 1.3 for all external traffic, mTLS for internal
- **Video frames** processed in-memory, never written to disk unencrypted
- **Database backups** encrypted with GPG before upload to cold storage

### 14.4 AI Model Security
- **Model integrity checks** — both `yolo11m.pt` and `best.pt` verified by SHA-256 before loading
- **Input sanitization** to prevent adversarial perturbations
- **Graceful degradation** — if health model fails, counting still works (and vice versa)
- **RTSP password redaction** — camera URLs logged without credentials

---

## 15. MLOps Pipeline

### 15.1 Dataset Management
- **Labeling tool:** CVAT self-hosted instance for annotating new camera frames
- **Dataset versioning:** DVC (Data Version Control) tracks dataset snapshots
- **Augmentation pipeline:** Albumentations (random crop, rotate, brightness, mosaic, mixup)
- **Label review workflow:** Auto-check → Peer review → Approved for training

### 15.2 Training Pipeline
- **Trigger:** Manual (via dashboard "Retrain Model" button) or scheduled (bi-weekly)
- **Training infra:** Same GPU server, dedicated Docker Compose profile
- **Hyperparameter tracking:** MLflow (learning rate, batch size, optimizer, loss curves)
- **Experiment comparison:** MLflow UI compares mAP50, mAP95, precision, recall across runs

### 15.3 Model Registry
- **Staging:** Model trained, validated on hold-out set, passes quality gates
- **Production:** Model deployed to inference workers, replaces previous version
- **Rollback:** One-click revert to any previous model version via MLflow
- **Quality gates:** mAP50 ≥ 85%, inference latency ≤ 150ms, false positive rate ≤ 2%

### 15.4 Continuous Improvement
- **Active learning loop:** Low-confidence predictions auto-flagged for labeling
- **Edge case capture:** Frames with false positives/negatives stored (blurred faces) for retraining
- **Shadow deployment:** New model runs alongside production for 24h comparison before cutover
- **Drift detection:** Monitor accuracy degradation over time; trigger retrain when mAP drops 5%

---

## 16. Observability & Monitoring

### 16.1 Logging
- **Centralized logging:** Grafana Loki collects all container logs
- **Structured logging:** JSON format with request ID, service name, timestamp, severity
- **Log retention:** 30 days hot (Loki), 1 year cold (S3-compatible archive)

### 16.2 Metrics
- **Prometheus metrics** exported from every service (API, workers, DB, Redis)
- **Key metrics:** Inference latency (p50/p95/p99), detection event rate, API response time, MQTT event lag
- **Custom metrics:** Chickens detected per frame, health score distribution, per-camera processing time

### 16.3 Alerting
- **Grafana Alerting** with multiple notification channels (Email, Telegram, Slack)
- **Critical alerts:** GPU temperature > 85°C, Frigate pipeline stalled > 120s, camera offline > 5 min
- **Warning alerts:** Model confidence drop, frame loss > 5%, disk usage > 80%

### 16.4 Dashboards
- **System health dashboard:** GPU utilization, memory, disk I/O, network throughput
- **Pipeline dashboard:** Frames in/sec, inference time, queue depth, error rate
- **Business dashboard:** Active chickens, alerts/hour, health score distribution (reuses Grafana)

---

## 17. Backup & Disaster Recovery

### 17.1 Backup Schedule
| Data | Frequency | Retention | Storage |
|------|-----------|-----------|---------|
| PostgreSQL | Daily | 30 days | Local + S3 |
| InfluxDB | Hourly | 7 days | Local |
| MinIO objects | Continuous (sync) | 90 days | S3-compatible |
| Model weights | Per-version | Indefinite | MLflow + S3 |
| Config files | Per-change | Indefinite | Git |
| Logs | Continuous | 30d hot / 1y cold | Loki + S3 |

### 17.2 Recovery Procedures
- **RPO (Recovery Point Objective):** 1 hour (acceptable data loss)
- **RTO (Recovery Time Objective):** 4 hours (acceptable downtime)
- **Warm standby:** Secondary GPU server with pre-loaded models, can take over within 10 min
- **Restore drill:** Full recovery test every quarter

### 17.3 Failure Scenarios
- **GPU failure:** Orchestrator stops → restart backend container → detection resumes on next cycle
- **Database corruption:** Point-in-time recovery from WAL archives (PostgreSQL)
- **Entire device loss:** Provision new Jetson, restore from S3 backups

---

## 18. Network Architecture

### 18.1 Topology

**Single-site (all cameras + GPU server on same LAN):**

```
[Cameras] --RTSP--> [Existing NVR] --RTSP relay--> [GPU Server]
     |                                                  |
     |--- direct RTSP (fallback) -----------------------|
                                 |
                          [VLAN 10 - Cameras]
                                 |
                          [Firewall/Router]
                                 |
                    +------------+------------+
                    |                         |
              [VLAN 20 - GPU Server]    [VLAN 30 - Office LAN]
                    |                         |
              [GPU Server]              [Admin Dashboard]
              (API, Workers, DB)         (Laptop/Desktop)
```

**Multi-farm (Tailscale subnet routing):**

```
  ┌─────────────────────────────────────────────────────────────────┐
  │                       TAILSCALE MESH VPN                         │
  │  (encrypted WireGuard — no ports open on any firewall)          │
  └─────────────────────────────────────────────────────────────────┘
         │                   │                    │
         ▼                   ▼                    ▼
  ┌──────────────┐   ┌──────────────┐   ┌──────────────────┐
  │  Farm A       │   │  Farm B       │   │  GPU Server       │
  │  subnet:      │   │  subnet:      │   │  (Docker Host)    │
  │  192.168.1.0  │   │  10.0.0.0    │   │                   │
  │               │   │              │   │  tailscale up     │
  │  RPi ─────────┤   │  RPi ────────┤   │  --accept-routes  │
  │  --advertise- │   │  --advertise-│   │                   │
  │  routes       │   │  routes      │   │  Frigate reaches  │
  │               │   │              │   │  192.168.1.50:554 │
  │  Cameras:     │   │  Cameras:    │   │  via Tailscale    │
  │  192.168.1.50 │   │  10.0.0.50   │   │  (no Docker       │
  │  ..70         │   │  ..70        │   │   changes needed) │
  └──────────────┘   └──────────────┘   └──────────────────┘

  ┌──────────────┐
  │  Farm C       │
  │  subnet:      │
  │  172.16.0.0   │
  │               │
  │  RPi ──────── │
  │  --advertise- │
  │  routes       │
  └──────────────┘
```

Each farm runs a small Tailscale node (Raspberry Pi, spare laptop, or the NVR) as a **subnet router**, advertising the camera LAN subnet. The GPU server installs Tailscale on the **Docker host** with `--accept-routes`. Docker containers inherit the host's routing table, so Frigate reaches camera RTSP URLs by their local IP with zero Docker configuration changes.

For remote admin dashboard access, **Tailscale Serve** can expose the frontend:
```bash
sudo tailscale serve --bg --https=443 http://localhost:3000
```

### 18.2 Bandwidth Requirements
- **Single camera:** 1080p @ 15 FPS = ~4 Mbps (H.264) — Frigate ingests continuously
- **16 cameras:** ~64 Mbps peak (RTSP streams ingested by Frigate 24/7)
- **Recommended:** All cameras + NVR + server on dedicated Gigabit switch
- **Note:** Frigate's go2rtc re-streams HLS independently; health/MCMT processing is event-driven

### 18.3 Latency Budget
| Segment | Budget |
|---------|--------|
| Camera → Frigate (RTSP) | ≤ 50ms |
| Frigate motion → bird detection → MQTT publish | ≤ 300ms |
| MQTT → backend subscriber → snapshot download | ≤ 200ms |
| Health classifier + MCMT inference | ≤ 300ms |
| InfluxDB write + WebSocket broadcast | ≤ 100ms |
| Dashboard refresh (hls.js) | ≤ 3s (HLS segment) |
| **Total pipeline (event → notification)** | **≤ 1s** |

---

## 19. External Integrations

### 19.1 Supported Integrations
- **Existing NVRs:** Hikvision, Dahua, Uniview, Milestone, Blue Iris (RTSP/ONVIF)
- **IoT sensors:** Modbus TCP for temperature/humidity/ammonia sensors
- **Weighing systems:** Optional integration with poultry weighing platforms
- **Farm management software:** Export health reports via CSV/JSON API
- **SMS/Email gateways:** Twilio for critical alerts, SendGrid for daily summaries

### 19.2 Webhook API
- Configurable webhook URLs for alert events
- Payload: `{ chicken_id, alert_type, severity, timestamp, snapshot_url }`
- Retry with exponential backoff (3 attempts)
- HMAC signature for authenticity verification

---

## 20. User Roles & Device Support

### 20.1 User Roles

The system implements **role-based access control (RBAC)** scoped by farm. Every user (except super admin) belongs to exactly one farm.

| Role | Scope | Permissions |
|------|-------|-------------|
| **Viewer** | Single farm | View dashboard, browse history, acknowledge alerts |
| **Operator** | Single farm | Viewer + manage chickens (add/remove/rename), adjust alert thresholds |
| **Admin** | Single farm | Operator + user management for their farm, system config |
| **Super Admin** | **All farms** | Full access across every farm: create/edit/delete farms, manage all users, impersonate any user, audit logs, backup management, role assignment, all cameras/chickens/alerts |

**Key rules for super admin:**
- Exactly **one super admin** exists at the company level (created by seed script as `admin@poultry.farm`)
- The super admin sees all farms in a **farm switcher dropdown** (header + sidebar)
- All data queries filter by the selected farm via `X-Farm-ID` header
- The super admin can **impersonate** any user to debug permission or data-visibility issues
- While impersonating, a yellow banner shows *"Viewing as {name} ({role})"* with a **Stop Impersonating** button
- No farm user can create or delete the super admin

### 20.2 Device Support
- **Desktop:** Full dashboard (Chrome, Firefox, Edge)
- **Tablet:** Responsive layout optimized for iPad (landscape) and Android tablets
- **Mobile:** Essential views (active alerts, chicken list, quick health check)
- **TV/Screen:** Kiosk mode for coop-mounted displays showing live health dashboard

---

## 21. Performance Benchmarks & Targets

### 21.1 Baseline Targets
| Metric | Target | Degradation Threshold |
|--------|--------|----------------------|
| AI inference (counting + health, per frame) | ≤ 300ms | ≥ 500ms |
| Round-robin cycle time (16 cameras) | ≤ 55s | ≥ 120s |
| API response (p95) | ≤ 200ms | ≥ 500ms |
| Dashboard page load | ≤ 2s | ≥ 5s |
| Live video latency (HLS) | ≤ 3s | ≥ 10s |
| Concurrent users | 10 | 20 |
| Concurrent cameras | 16 | 24 |
| Maximum chickens tracked | 200 | 500 |
| Data retention (hot) | 30 days | — |

### 21.2 Scaling Strategy
- **Vertical:** Upgrade to Jetson Orin NX 16 GB or dedicated GPU (RTX 4060+), more RAM
- **Horizontal:** Additional Jetson devices with split camera assignment (8 cameras each)
- **Database:** Read replicas for dashboard queries; time-series partitioning for InfluxDB
- **Caching:** Redis TTL tuning; CDN for static dashboard assets
- **Faster cycle:** Reduce `CAMERA_PROCESS_INTERVAL` for fewer cameras

---

## 22. Operations & Maintenance

### 22.1 Routine Tasks
| Frequency | Task | Expected Duration |
|-----------|------|-------------------|
| Daily | Verify all cameras streaming, check alert log | 15 min |
| Weekly | Review model confidence trends, flag low-confidence IDs | 30 min |
| Bi-weekly | Retrain model if drift detected, review edge case captures | 2 hr |
| Monthly | Backup verification, log rotation check, security patch audit | 1 hr |
| Quarterly | Full DR drill, model performance deep-dive, capacity planning | 4 hr |

### 22.2 Runbook (Common Incidents)
| Incident | Immediate Action | Resolution |
|----------|-----------------|------------|
| Camera offline | Check RTSP endpoint, restart camera via NVR | 5-15 min |
| Inference slow | Check GPU utilization, restart backend container | 2-5 min |
| Detection pipeline stalled | Check Frigate logs, restart backend subscriber | 1-3 min |
| Model crash | Auto-fallback to previous model version (config reload) | 30 sec |
| DB connection error | Restart DB container, verify WAL consistency | 5-10 min |

### 22.3 Capacity Planning
- **Storage projection:** ~100 GB/month for metadata + snapshots + logs (Jetson edge)
- **GPU compute:** Jetson Orin Nano runs Frigate for 16 cameras + health classifier on detection events
- **Memory:** 8 GB shared (Jetson Orin Nano); 16 GB+ for GPU server
- **Disk:** 128 GB NVMe minimum; 512 GB+ recommended for logs + snapshots
- **Power:** Jetson Orin Nano ~15W TDP; GPU server ~500W TDP

---

## 23. Cost Estimation

### 23.1 One-Time Setup Costs
| Item | Estimated Cost |
|------|---------------|
| Jetson Orin Nano 8 GB Developer Kit | $499 |
| 128 GB NVMe SSD (for Jetson) | $30–$50 |
| Power supply (already included with dev kit) | $0 |
| Network switch (Gigabit, managed, 24-port) | $200–$400 |
| Cabling & installation | $500–$1,000 |
| **Total setup (Jetson edge)** | **$1,230–$1,950** |
| **Total setup (GPU server)** | **$4,000–$7,900** |

*Note: Cameras and NVR are existing — not included.*

### 23.2 Monthly Operational Costs
| Item | Estimated Cost |
|------|---------------|
| Electricity (Jetson Orin Nano ~15W vs GPU server ~500W) | $2–$5 (Jetson) / $60–$120 (server) |
| Internet (existing — negligible increment) | $0–$20 |
| Cloud backup (S3-compatible, ~50 GB) | $5–$10 |
| SMS alerts (Twilio, ~200 messages/month) | $10–$20 |
| Domain & SSL certificate (via Cloudflare) | $0–$5 |
| Cloudflare Tunnel (free tier) | $0 |
| **Total monthly (Jetson)** | **$17–$60** |
| **Total monthly (GPU server)** | **$75–$185** |

### 23.3 Optional Cloud GPU (DR/overflow)
| GPU Type | Cost/Hour |
|----------|-----------|
| NVIDIA RTX 4090 (cloud) | $0.50–$0.80 |
| NVIDIA A100 (cloud) | $1.50–$3.00 |

---

## 24. Privacy & Compliance

### 24.1 Data Privacy
- **Video data** is processed entirely on-device (Jetson); no video leaves the farm LAN unless Cloudflare Tunnel is enabled
- **Cloudflare Tunnel** exposes the dashboard only; no video bypasses HTTPS
- **Access logs** record every user action (who viewed what, when)
- **Data retention policy:** Detection snapshots kept 7 days; derived data (health scores, counts) retained 1 year

### 24.2 Compliance Considerations
- **No PII (Personally Identifiable Information)** is collected — chicken IDs are farm-internal labels
- **GDPR readiness:** Data deletion on request, access logs available, data processing register maintained
- **Biosecurity:** Remote access requires VPN; all farm visits logged
- **Audit trail:** Immutable audit log for all configuration changes, model deployments, and user actions

---

## 25. Next Steps & Client Action Items

1. **Apply multi-farm migration:** Run `alembic upgrade head` on existing databases. Fresh installs auto-create everything via `init_db()`.
2. **Create farms and users:** Login as super admin → create farms → assign farm admins → add cameras/chickens per farm
3. **Test data isolation:** Verify a farm user sees only their farm's data; super admin sees all via farm switcher
4. **Deploy on Jetson Orin Nano:** Install Docker + nvidia-container-runtime, export models to TensorRT, run `docker compose up -d`
5. **Set up Cloudflare Tunnel** for internet exposure (free tier — no open ports)
6. **Replace placeholder RTSP URLs** in `seed_real_cameras.py` with actual camera addresses
7. **Configure `.env`** with canonical domain values (`VITE_API_URL=https://your-domain.com`, `CORS_ORIGINS=https://your-domain.com`)
8. **Test Frigate detection** — verify cameras appear in Frigate UI, MQTT events trigger health classification

---

## Appendix A: Glossary

| Term | Definition |
|------|------------|
| **RTSP** | Real-Time Streaming Protocol — used to access live video from IP cameras |
| **NVR** | Network Video Recorder — records camera feeds 24/7 |
| **Frigate** | Open-source NVR with built-in object detection, motion detection, and go2rtc streaming |
| **go2rtc** | Embedded streaming server in Frigate providing HLS, WebRTC, and MSE playback |
| **MQTT** | Lightweight publish/subscribe messaging protocol (Mosquitto broker) used as Frigate's event bus |
| **YOLO11** | You Only Look Once v11 — real-time object detection model (used in HealthClassifier) |
| **MCMT** | Multi-Camera Multi-Target tracking — cross-camera identity matching using ReID + FAISS |
| **MiewID** | Re-identification model that generates feature embeddings for chicken identity matching |
| **FAISS** | Facebook AI Similarity Search — vector database for fast identity lookup |
| **TensorRT** | NVIDIA's model optimization engine — converts `.pt` to `.engine` for Jetson GPU acceleration |
| **InfluxDB** | Time-series database optimized for metrics and sensor data |
| **MinIO** | S3-compatible object store for video segments and snapshots |
| **HLS.js** | JavaScript HLS player used in the browser dashboard for live video |
| **VLAN** | Virtual Local Area Network — network segmentation for security |
| **RPO/RTO** | Recovery Point Objective / Recovery Time Objective — DR metrics |

---

## Appendix B: AI Model Cards

### Model: Chicken Counter (Counting Model)
| Field | Value |
|-------|-------|
| **Architecture** | YOLO11m |
| **Task** | Object detection (1 class: chicken) — counts all visible chickens |
| **Input size** | 640 × 640 |
| **Framework** | Ultralytics YOLO (PyTorch) |
| **Model file** | `AI_MODEL/yolo11m.pt` (SHA-256: `d5ffc1a6...`) |
| **Inference** | ~80ms on RTX 4090, ~200ms on Jetson Orin Nano (FP16) |
| **Quantization** | FP16 / TensorRT `.engine` for deployment |
| **Usage** | Runs on every frame. Assigns ByteTrack IDs for per-chicken counting. |

### Model: Chicken Health Classifier (Health Model)
| Field | Value |
|-------|-------|
| **Architecture** | YOLO11m (fine-tuned) |
| **Task** | Health classification (healthy / sick / injured / dead) |
| **Input size** | 640 × 640 |
| **Framework** | Ultralytics YOLO (PyTorch) |
| **Model file** | `AI_MODEL/best.pt` (SHA-256: `30d40416...`) |
| **Inference** | ~80ms on RTX 4090, ~200ms on Jetson Orin Nano (FP16) |
| **Quantization** | FP16 / TensorRT `.engine` for deployment |
| **Usage** | Runs on same frame as counting model. Both models process the same input independently — no chained pipeline. |

---

## Appendix C: Data Flow Diagrams

### C.1 Frigate Detection → Health Pipeline
```
Camera RTSP → Frigate ingests 24/7
  → Motion detected → Bird detected by Frigate detector
  → MQTT event: frigate/<cam>/events/new
  → Backend subscriber receives event (label="bird")
    → Downloads snapshot from Frigate API
    → Crops bird bbox from snapshot
    → Runs MCMT tracker (MiewID + FAISS) → global_id
    → Runs HealthClassifier (best.pt) → health class + confidence
    → Writes to InfluxDB (detections + health measurements)
    → Broadcasts via WebSocket (global_id, bbox, health results)
    → Alert rule evaluator checks thresholds → triggers alert if needed
```

### C.2 Alert Path — Sick Chicken Detected
```
HealthClassifier outputs health_class="unhealthy" with confidence > threshold
  → save snapshot to MinIO → create alert record in PostgreSQL → 
  → publish alert via WebSocket → dashboard toast notification → 
  → webhook call (if configured) → SMS/Email notification
```

### C.3 Feed Consumption Path
```
End user opens dashboard (browser) →
  → nginx proxies /api/frigate/hls/ to Frigate go2rtc (:1984)
  → HLS.js plays HLS stream in browser
  → WebSocket receives real-time detection + health events
  → Dashboard overlays detection boxes + health status on video
```

### C.4 Retraining Path — Model Improvement
```
HealthClassifier inference → low-confidence predictions flagged →
  → snapshots stored to MinIO → reviewed and labeled in CVAT →
  → added to training dataset (DVC tracked) →
  → health model retrained → quality gates passed →
  → new best.pt deployed → hot-replaced in backend subscriber
```

---

> **Document Version:** 4.0  
> **Last Updated:** June 2026  
> **Prepared for:** Client Review
