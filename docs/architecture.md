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

The Poultry Monitoring System is a **web-based application** that uses AI cameras to automatically:

- **Detect** every chicken in the coop in real time
- **Identify** each individual chicken by name/ID
- **Track** movement and behavior across cameras
- **Monitor health** through visual analysis and optional IoT sensors
- **Alert** farm staff when a chicken shows signs of illness or distress
- **Report** trends and analytics over days, weeks, and months

The system processes live video from 5–20 IP cameras installed in the poultry house, runs AI models on each frame, and displays everything on an easy-to-read web dashboard accessible from any device.

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

This is the "engine room." Frames from all cameras are processed by Celery workers — these are background programs that can run on one or more computers.

```
 ┌──────────────────────────────────────────────────────────────────┐
 │                    PROCESSING LAYER                               │
 │                                                                   │
 │  ┌──────────────────┐                                             │
 │  │  Celery Worker 1 │  (GPU-powered, handles Camera 1-5)         │
 │  │  ┌──────────────┐│                                             │
 │  │  │ 1. Grab frame││  Reads latest frame from RTSP stream       │
 │  │  │ 2. Detect    ││  Finds all chickens in the frame           │
 │  │  │ 3. Track     ││  Assigns stable IDs to each chicken        │
 │  │  │ 4. Identify  ││  Matches to known chicken (1 of 50)        │
 │  │  │ 5. Analyze   ││  Computes health metrics                   │
 │  │  │ 6. Store     ││  Saves to DB + sends to dashboard          │
 │  │  └──────────────┘│                                             │
 │  └──────────────────┘                                             │
 │                                                                   │
 │  ┌──────────────────┐                                             │
 │  │  Celery Worker 2 │  (same pipeline, Camera 6-10)              │
 │  └──────────────────┘                                             │
 │                                                                   │
 │  If you have 5-20 cameras, you can add more workers as needed.    │
 └──────────────────────────────────────────────────────────────────┘
```

**Why Celery workers?**
- Each camera takes about 100-200ms to process per frame
- With 10 cameras at 5 FPS, that's 50 frames/second = up to 10 seconds of processing per second
- Workers distribute this load across multiple GPU cores
- You can start with 1 worker and add more as you add cameras

---

### 3.3 AI Inference Pipeline

This is the **brain** of the system. It uses two YOLOv8 AI models working together:

```
 ┌───────────────────────────────────────────────────────────────┐
 │                    TWO-STAGE AI PIPELINE                      │
 │                                                               │
 │                    RAW CAMERA FRAME                            │
 │                           │                                    │
 │                           ▼                                    │
 │  ┌───────────────────────────────────────────┐                │
 │  │ STAGE 1: CHICKEN DETECTOR                │                │
 │  │                                           │                │
 │  │  Model: YOLOv8n (fine-tuned on coop)     │                │
 │  │  Job: Find every chicken in the image     │                │
 │  │  Output: Bounding boxes around chickens   │                │
 │  │                                           │                │
 │  │  ┌──────────────────────────────────┐     │                │
 │  │  │  ┌──────┐   ┌──────┐   ┌──────┐ │     │                │
 │  │  │  │Chick │   │Chick │   │Chick │ │     │                │
 │  │  │  │en #1 │   │en #2 │   │en #3 │ │     │                │
 │  │  │  └──────┘   └──────┘   └──────┘ │     │                │
 │  │  └──────────────────────────────────┘     │                │
 │  └──────────────────┬────────────────────────┘                │
 │                     │                                         │
 │                     ▼                                         │
 │         ┌─────────────────────────┐                           │
 │         │  ByteTrack Tracker      │                           │
 │         │  Assigns a temporary ID │                           │
 │         │  to each chicken so we  │                           │
 │         │  follow it across frames│                           │
 │         └───────────┬─────────────┘                           │
 │                     │                                         │
 │                     ▼                                         │
 │  ┌───────────────────────────────────────────┐                │
 │  │ STAGE 2: RE-ID CLASSIFIER                │                │
 │  │                                           │                │
 │  │  Model: Your existing 50-chicken model   │                │
 │  │  Job: Identify WHICH chicken this is     │                │
 │  │  Output: Chicken ID (0-49) + confidence  │                │
 │  │                                           │                │
 │  │  Example:                                 │                │
 │  │  ┌──────────┐ ┌──────────┐ ┌──────────┐  │                │
 │  │  │ ID: #17  │ │ ID: #33  │ │ ID: #05  │  │                │
 │  │  │ 92% sure │ │ 87% sure │ │ 78% sure │  │                │
 │  │  └──────────┘ └──────────┘ └──────────┘  │                │
 │  └───────────────────────────────────────────┘                │
 │                                                               │
 └───────────────────────────────────────────────────────────────┘
```

**Why two stages?**
- Your current model was trained on images where one chicken fills the entire frame
- In real camera feeds, multiple chickens appear in one frame
- Stage 1 finds each chicken, Stage 2 identifies it
- This is the industry-standard approach for re-identification systems

---

### 3.4 Health Analysis Engine

After a chicken is identified, the system analyzes its health using five factors:

```
 ┌──────────────────────────────────────────────────────────────┐
 │                    HEALTH SCORING ENGINE                      │
 │                                                              │
 │  For each detected chicken, we compute:                      │
 │                                                              │
 │  ┌──────────────────────────────────────────────────────┐    │
 │  │  ACTIVITY SCORE (40% of total)                       │    │
 │  │                                                      │    │
 │  │  How much is this chicken moving?                    │    │
 │  │  - Tracks position across frames                     │    │
 │  │  - Compares to this chicken's normal activity level  │    │
 │  │  - Sudden drop → possible illness                    │    │
 │  │                                                      │    │
 │  │  Example: Chicken #17 normally moves 200px/s         │    │
 │  │  Today: 20px/s → Activity Score = 10/100             │    │
 │  └──────────────────────────────────────────────────────┘    │
 │                                                              │
 │  ┌──────────────────────────────────────────────────────┐    │
 │  │  POSTURE SCORE (25% of total)                        │    │
 │  │                                                      │    │
 │  │  Is the chicken standing normally?                   │    │
 │  │  - Standing chicken = tall, narrow bounding box      │    │
 │  │  - Sick/huddled chicken = short, wide bounding box   │    │
 │  │  - Sudden change in posture = potential issue        │    │
 │  └──────────────────────────────────────────────────────┘    │
 │                                                              │
 │  ┌──────────────────────────────────────────────────────┐    │
 │  │  SOCIAL SCORE (15% of total)                         │    │
 │  │                                                      │    │
 │  │  Is the chicken staying with the flock?              │    │
 │  │  - Measures distance to nearest chicken              │    │
 │  │  - Sick chickens often isolate themselves            │    │
 │  │  - Far from flock for >15 min → alert                │    │
 │  └──────────────────────────────────────────────────────┘    │
 │                                                              │
 │  ┌──────────────────────────────────────────────────────┐    │
 │  │  SENSOR SCORE (20% of total)                         │    │
 │  │                                                      │    │
 │  │  What do the environmental sensors say?              │    │
 │  │  - Temperature, humidity, ammonia levels             │    │
 │  │  - Outside optimal range → environmental stress      │    │
 │  │  - Requires optional IoT sensor hardware             │    │
 │  └──────────────────────────────────────────────────────┘    │
 │                                                              │
 │  ┌──────────────────────────────────────────────────────┐    │
 │  │  FINAL HEALTH SCORE = Weighted average 0-100         │    │
 │  │                                                      │    │
 │  │  Green  (80-100): Healthy, normal                    │    │
 │  │  Yellow (50-79):  Needs monitoring                   │    │
 │  │  Orange (30-49):  Needs attention                    │    │
 │  │  Red    (0-29):   Critical — alert triggered         │    │
 │  └──────────────────────────────────────────────────────┘    │
 │                                                              │
 │  Health scores are recalculated every time a chicken is      │
 │  detected (typically every 1-5 seconds).                     │
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
 │  chickens ────┬─── detection_events ────┬─── cameras          │
 │  ┌────────┐   │    ┌────────────────┐   │    ┌────────┐      │
 │  │ id     │   │    │ id             │   │    │ id     │      │
 │  │ class  │◄──┘    │ chicken_id     │◄──┘    │ name   │      │
 │  │ name   │         │ camera_id     │◄────────│ rtsp   │      │
 │  │ breed  │         │ track_id      │         │ loc    │      │
 │  │ status │         │ bbox (coords) │         │ active │      │
 │  │ color  │         │ confidence    │         │ config │      │
 │  │ photo  │         │ snapshot_url  │         └────────┘      │
 │  └────────┘         │ timestamp     │                          │
 │       │             └───────────────┘                          │
 │       │                   │ (partitioned by month)             │
 │       │                   │                                    │
 │       │    alerts ────────┤                                    │
 │       │    ┌──────────────┴───┐                               │
 │       │    │ id               │                               │
 │       ├────│ chicken_id       │                               │
 │       │    │ camera_id        │                               │
 │       │    │ type             │                               │
 │       │    │ severity         │                               │
 │       │    │ message          │                               │
 │       │    │ resolved         │                               │
 │       │    │ created_at       │                               │
 │       │    └──────────────────┘                               │
 │       │                                                       │
 │       │    health_scores                                      │
 │       │    ┌──────────────────┐                               │
 │       └────│ chicken_id      │                               │
 │            │ overall         │                               │
 │            │ activity        │                               │
 │            │ posture         │                               │
 │            │ social          │                               │
 │            │ sensor          │                               │
 │            │ timestamp       │                               │
 │            └──────────────────┘                               │
 │                                                               │
 │  users              alert_rules                               │
 │  ┌──────────────┐   ┌──────────────────┐                     │
 │  │ id           │   │ id               │                     │
 │  │ email        │   │ name             │                     │
 │  │ password     │   │ metric           │                     │
 │  │ role         │   │ operator         │                     │
 │  │ created_at   │   │ threshold        │                     │
 │  └──────────────┘   │ duration_min     │                     │
 │                     │ severity         │                     │
 │                     │ enabled          │                     │
 │                     └──────────────────┘                     │
 └───────────────────────────────────────────────────────────────┘
```

### 7.2 InfluxDB (Time-Series Data)

| Data Type | What's Stored | Retention |
|---|---|---|
| **Detections** | Every time a chicken is seen: chicken ID, camera, location in frame, confidence | 30 days raw, 1 year hourly avg |
| **Health Scores** | Per-chicken health score every time it's calculated | 30 days raw, forever daily avg |
| **Activity Logs** | Movement speed, distance traveled between frames | 30 days raw, 1 year hourly avg |
| **Sensor Readings** | Temperature, humidity, ammonia per camera location | 30 days raw, forever hourly avg |

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
 │    POST /auth/register          Create account                 │
 │    POST /auth/login             Login (returns JWT)           │
 │    POST /auth/refresh           Refresh access token           │
 │    POST /auth/logout            Invalidate session             │
 │    GET  /auth/me                Current user profile           │
 │    POST /auth/change-password   Update password                │
 │    GET  /auth/users             List all users (admin)        │
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
 │  │  ● Celery                    — Background task queue    │  │
 │  │  ● Redis                     — Cache + task broker      │  │
 │  │  ● JWT                       — Authentication           │  │
 │  └─────────────────────────────────────────────────────────┘  │
 │                                                               │
 │  ┌─────────────────────────────────────────────────────────┐  │
 │  │  AI / ML                                                │  │
 │  │  ───────                                                │  │
 │  │  ● Ultralytics YOLOv8n      — Object detection model   │  │
 │  │  ● PyTorch                  — Deep learning framework   │  │
 │  │  ● ByteTrack                — Multi-object tracking     │  │
 │  │  ● OpenCV                   — Image processing          │  │
 │  │  ● ONNX / TensorRT          — Model optimization        │  │
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
 │  │  ● Traefik / Nginx           — Reverse proxy + SSL     │  │
 │  └─────────────────────────────────────────────────────────┘  │
 └───────────────────────────────────────────────────────────────┘
```

---

## 11. Deployment Architecture

The system runs as a set of **Docker containers** that can be deployed on a single server or distributed across multiple machines.

```
 ┌───────────────────────────────────────────────────────────────┐
 │                    DEPLOYMENT ARCHITECTURE                     │
 │                                                               │
 │                   ┌─────────────────────┐                     │
 │                   │   Your Computer     │                     │
 │                   │   (Web Browser)     │                     │
 │                   │   Dashboard UI      │                     │
 │                   └──────────┬──────────┘                     │
 │                              │ HTTPS                          │
 │                              ▼                                │
 │              ┌───────────────────────────────┐                │
 │              │          SERVER / GPU PC       │                │
 │              │    (Docker Host — Windows/Linux)│               │
 │              │                               │                │
 │              │  ┌─────────────────────────┐  │                │
 │              │  │  Traefik (Reverse Proxy) │  │                │
 │              │  └──────────┬──────────────┘  │                │
 │              │             │                  │                │
 │              │  ┌──────────┴──────────────┐  │                │
 │              │  │  FastAPI Backend         │  │                │
 │              │  │  (REST + WebSocket)      │  │                │
 │              │  └──────────┬──────────────┘  │                │
 │              │             │                  │                │
 │              │  ┌──────────┴──────────────┐  │                │
 │              │  │  Celery Workers (GPU)   │  │                │
 │              │  │  ● Frame Grabber        │  │                │
 │              │  │  ● Chicken Detector     │  │                │
 │              │  │  ● Re-ID Classifier     │  │                │
 │              │  │  ● Health Analyzer      │  │                │
 │  ─ ─ ─ ─ ─  │  └─────────────────────────┘  │  ─ ─ ─ ─ ─ ─  │
 │   Optional  │  ┌──────────┐ ┌──────────┐ ┌──────┐            │
 │   GPU       │  │PostgreSQL│ │ InfluxDB │ │Redis │            │
 │   Server    │  └──────────┘ └──────────┘ └──────┘            │
 │             │  ┌──────────┐  ┌──────────┐                    │
 │             │  │ MinIO/S3 │  │ Frontend │                    │
 │             │  └──────────┘  │ (React)  │                    │
 │             │               └──────────┘                    │
 │             └───────────────────────────────────────────────┘│
 │                                                              │
 │  ┌──────────────────────────────────────────────────────┐    │
 │  │  CAMERA NETWORK (Already Deployed)                   │    │
 │  │                                                      │    │
 │  │  ┌──────────────┐                                    │    │
 │  │  │  NVR          │  Records 24/7 to HDD              │    │
 │  │  │  (Existing)   │  Manages camera configs           │    │
 │  │  └──────┬───────┘                                    │    │
 │  │         │                                            │    │
 │  │  Camera 1 ──RTSP──┤                                  │    │
 │  │  Camera 2 ──RTSP──┤  Same local network as           │    │
 │  │  Camera 3 ──RTSP──┤  our GPU server                  │    │
 │  │  ...              │                                  │    │
 │  │  Camera 20 ──RTSP─┘                                  │    │
 │  │                                                      │    │
 │  │  Cameras feed BOTH the NVR (recording)               │    │
 │  │  and our server (AI analysis) — no conflict.         │    │
 │  └──────────────────────────────────────────────────────┘    │
 │                                                              │
 │  Optional: IoT sensor hub for temperature, humidity, etc.    │
 └───────────────────────────────────────────────────────────────┘
```

**Hardware Recommendation:**
- **GPU Server:** PC with NVIDIA GPU (RTX 3060 or better, 8GB+ VRAM)
- **RAM:** 16GB+
- **Storage:** 500GB SSD (for database + snapshots)
- **Network:** Gigabit Ethernet (all cameras + server on same switch)

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

> **Think of YOLOv8 as a super-fast pattern matcher.**
>
> During training, we showed the model thousands of photos of each chicken. The model learned to recognize patterns — feather colors, comb shapes, body sizes, and unique markings.
>
> When a new camera frame comes in:
> 1. The model scans the entire image in one pass
> 2. It identifies every chicken-shaped object
> 3. It draws a box around each one
> 4. It compares each chicken against its memory of all 50 chickens
> 5. It picks the best match and reports how confident it is
>
> The entire process takes about **100 milliseconds per frame** — faster than a human blink.
>
> The current model achieved **80.9% mean Average Precision (mAP50)** on validation tests. This means when it identifies a chicken, it's correct about 4 out of 5 times. With more training data and camera-specific fine-tuning, this can improve to 90%+.

---

> **Document Version:** 1.1  
> **Last Updated:** June 2026  
> **Prepared for:** Client Review

---

## 14. Security Architecture

### 14.1 Network Security
- **VLAN segmentation:** Cameras, NVR, GPU server, and office LAN on separate VLANs
- **Firewall rules:** GPU server can initiate RTSP connections; cameras cannot reach GPU server
- **mTLS** between all internal microservices (Celery workers, API server, databases)
- **WireGuard VPN** for remote admin access; no open SSH/RDP ports

### 14.2 Application Security
- **JWT with short expiry** (15 min access, 7 day refresh) for dashboard auth
- **Role-based access control (RBAC):** Viewer, Operator, Admin, Super-admin
- **API rate limiting** (100 req/min per user, 1000 req/min per IP)
- **Input validation** on all API endpoints (Pydantic models with strict mode)
- **SQL injection prevention** via parameterized queries (SQLAlchemy)

### 14.3 Data Security
- **At-rest encryption:** PostgreSQL (TDE), MinIO (SSE-S3), InfluxDB (encryption enabled)
- **In-transit encryption:** TLS 1.3 for all external traffic, mTLS for internal
- **Video frames** processed in-memory, never written to disk unencrypted
- **Database backups** encrypted with GPG before upload to cold storage

### 14.4 AI Model Security
- **Model integrity checks** (SHA-256 hash verified before loading)
- **Input sanitization** to prevent adversarial perturbations
- **Inference sandboxing** (separate container, no network except Redis/DB)
- **Model access logging** (who loaded which model, when, result hash)

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
- **Key metrics:** Inference latency (p50/p95/p99), queue depth, API response time, frame loss rate
- **Custom metrics:** Chickens detected per frame, re-ID confidence, health score distribution

### 16.3 Alerting
- **Grafana Alerting** with multiple notification channels (Email, Telegram, Slack)
- **Critical alerts:** GPU temperature > 85°C, queue backlog > 1000 frames, consumer lag > 30s
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
- **GPU failure:** Celery workers drain tasks → standby server activates → queue replays unprocessed frames
- **Database corruption:** Point-in-time recovery from WAL archives (PostgreSQL)
- **Entire server loss:** Spin up cloud GPU instance (pre-configured AMI/image), restore from S3 backups

---

## 18. Network Architecture

### 18.1 Topology

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

### 18.2 Bandwidth Requirements
- **Single camera:** 1080p @ 15 FPS = ~4 Mbps (H.264)
- **5 cameras:** ~20 Mbps
- **20 cameras:** ~80 Mbps (requires Gigabit LAN)
- **Recommended:** All cameras + NVR + GPU server on dedicated Gigabit switch

### 18.3 Latency Budget
| Segment | Budget |
|---------|--------|
| Camera → GPU server (RTSP) | ≤ 50ms |
| Frame decode + resize | ≤ 30ms |
| AI inference (Stage 1 + Stage 2) | ≤ 120ms |
| Post-processing + DB write | ≤ 30ms |
| Dashboard refresh | ≤ 500ms |
| **Total pipeline** | **≤ 250ms per frame** |

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
| Role | Permissions |
|------|------------|
| **Viewer** | View dashboard, browse history, acknowledge alerts |
| **Operator** | Viewer + manage chickens (add/remove/rename), adjust alert thresholds |
| **Admin** | Operator + user management, system config, model deployment |
| **Super-admin** | Admin + audit log access, backup management, role assignment |

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
| AI inference (per frame) | ≤ 120ms | ≥ 200ms |
| API response (p95) | ≤ 200ms | ≥ 500ms |
| Dashboard page load | ≤ 2s | ≥ 5s |
| Live video latency | ≤ 1s | ≥ 3s |
| Concurrent users | 20 | 50 |
| Concurrent cameras | 20 | 30 |
| Maximum chickens tracked | 500 | 1000 |
| Data retention (hot) | 30 days | — |

### 21.2 Scaling Strategy
- **Vertical:** Upgrade GPU (RTX 4090 → A6000 → A100), add RAM, faster NVMe
- **Horizontal:** Additional GPU servers with load-balanced camera assignment
- **Database:** Read replicas for dashboard queries; time-series partitioning for InfluxDB
- **Caching:** Redis TTL tuning; CDN for static dashboard assets

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
| Inference slow | Check GPU utilization, restart Celery workers | 2-5 min |
| Queue backlog | Scale up worker count, skip non-critical frames | 1-3 min |
| Model crash | Auto-fallback to previous model version | 30 sec |
| DB connection error | Restart DB container, verify WAL consistency | 5-10 min |

### 22.3 Capacity Planning
- **Storage projection:** ~500 GB/month for video segments + metadata + logs
- **GPU compute:** Single RTX 4090 handles 8-12 cameras at 5 FPS
- **Memory:** 64 GB RAM recommended; InfluxDB + Redis benefit most
- **Disk:** 2 TB NVMe minimum; RAID 1 recommended for data safety

---

## 23. Cost Estimation

### 23.1 One-Time Setup Costs
| Item | Estimated Cost |
|------|---------------|
| GPU Server (custom build, RTX 4090, 64 GB, 2 TB NVMe) | $4,000–$6,000 |
| Network switch (Gigabit, managed, 24-port) | $200–$400 |
| UPS for server | $300–$500 |
| Cabling & installation | $500–$1,000 |
| **Total setup** | **$5,000–$7,900** |

*Note: Cameras and NVR are existing — not included.*

### 23.2 Monthly Operational Costs
| Item | Estimated Cost |
|------|---------------|
| Electricity (GPU server ~500W 24/7) | $60–$120 |
| Internet (existing — negligible increment) | $0–$20 |
| Cloud backup (S3-compatible, ~500 GB) | $10–$25 |
| SMS alerts (Twilio, ~200 messages/month) | $10–$20 |
| Domain & SSL certificate | $5–$15 |
| **Total monthly** | **$85–$200** |

### 23.3 Optional Cloud GPU (DR/overflow)
| GPU Type | Cost/Hour |
|----------|-----------|
| NVIDIA RTX 4090 (cloud) | $0.50–$0.80 |
| NVIDIA A100 (cloud) | $1.50–$3.00 |

---

## 24. Privacy & Compliance

### 24.1 Data Privacy
- **Video data** is processed and stored entirely on-premises; no video leaves the farm LAN
- **Anonymized snapshots** (blurred background, chickens only) used for cloud backup
- **Access logs** record every user action (who viewed what, when)
- **Data retention policy:** Raw video segments deleted after 7 days; derived data (health scores, detections) retained 1 year

### 24.2 Compliance Considerations
- **No PII (Personally Identifiable Information)** is collected — chicken IDs are farm-internal labels
- **GDPR readiness:** Data deletion on request, access logs available, data processing register maintained
- **Biosecurity:** Remote access requires VPN; all farm visits logged
- **Audit trail:** Immutable audit log for all configuration changes, model deployments, and user actions

---

## 25. Next Steps & Client Action Items

1. **Review this architecture document** and confirm assumptions (camera count, network topology, feature priorities)
2. **Confirm VLAN/firewall capabilities** with network admin — is a separate VLAN for the GPU server feasible?
3. **Provide test RTSP streams** from 2–3 cameras for AI model adaptation (varies by lighting, angle, breed)
4. **Share existing NVR make/model** to verify RTSP relay compatibility
5. **Decide on IoT sensor integration** — is temperature/humidity/ammonia monitoring desired in Phase 1?
6. **Choose Phase 1 scope:** Core detection + tracking + basic health dashboard (8 weeks), or expanded Phase 1 including sensors + alerts (12 weeks)

---

## Appendix A: Glossary

| Term | Definition |
|------|------------|
| **RTSP** | Real-Time Streaming Protocol — used to access live video from IP cameras |
| **NVR** | Network Video Recorder — records camera feeds 24/7 |
| **YOLOv8** | You Only Look Once v8 — real-time object detection model |
| **mAP50** | Mean Average Precision at 50% IoU threshold — standard detection accuracy metric |
| **ByteTrack** | Multi-object tracking algorithm that uses bounding box overlap |
| **Re-ID** | Re-identification — recognizing the same individual across different camera views |
| **Celery** | Distributed task queue for asynchronous AI inference |
| **InfluxDB** | Time-series database optimized for metrics and sensor data |
| **MinIO** | S3-compatible object store for video segments and snapshots |
| **VLAN** | Virtual Local Area Network — network segmentation for security |
| **mTLS** | Mutual TLS — two-way certificate-based authentication |
| **RPO/RTO** | Recovery Point Objective / Recovery Time Objective — DR metrics |

---

## Appendix B: AI Model Cards

### Model: Chicken Detector (Stage 1)
| Field | Value |
|-------|-------|
| **Architecture** | YOLOv8n |
| **Task** | Object detection (1 class: chicken) |
| **Input size** | 640 × 640 |
| **Framework** | Ultralytics YOLO (PyTorch) |
| **Training data** | Chicks4FreeID (curated frames) |
| **Target mAP50** | ≥ 92% |
| **Inference** | ~30ms on RTX 4090 |
| **Quantization** | FP16 (TensorRT for deployment) |

### Model: Chicken Re-ID Classifier (Stage 2)
| Field | Value |
|-------|-------|
| **Architecture** | YOLOv8n-cls (classification head) |
| **Task** | Individual identification (50 classes) |
| **Input size** | 224 × 224 (crop from detector) |
| **Framework** | Ultralytics YOLO (PyTorch) |
| **Training data** | Chicks4FreeID (50 individuals) |
| **Current mAP50** | 80.9% |
| **Target mAP50** | ≥ 90% |
| **Inference** | ~15ms per crop on RTX 4090 |

---

## Appendix C: Data Flow Diagrams

### C.1 Happy Path — Normal Operation
```
Camera → RTSP → FFmpeg decode → resize 640px → Stage 1 (detect) → 
  → ByteTrack (assign track ID) → crop each detection → 
  → Stage 2 (re-ID classify) → health analysis → 
  → write to InfluxDB + PostgreSQL → publish to Redis pub/sub → 
  → WebSocket push → dashboard update
```

### C.2 Alert Path — Sick Chicken Detected
```
Stage 2 → confidence low OR health score < threshold → 
  → save snapshot to MinIO → create alert record in PostgreSQL → 
  → publish alert to Redis pub/sub → dashboard toast notification → 
  → webhook call (if configured) → SMS/Email notification
```

### C.3 Retraining Path — Model Improvement
```
Production inference → low-confidence frames captured → 
  → labeled in CVAT → added to dataset (DVC tracked) → 
  → training triggered in MLflow → quality gates passed → 
  → new model version promoted to staging → shadow deployment → 
  → 24h comparison → promoted to production
```

---

> **Document Version:** 1.1  
> **Last Updated:** June 2026  
> **Prepared for:** Client Review
