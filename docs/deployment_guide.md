# VisionNav Remote Backend Deployment Guide

This guide documents the architecture, containerization, access protection, and hardware sizing for deploying the VisionNav vision inference backend on a remote host (cloud VM, bare-metal server, or private server) for access by the VisionNav mobile phone application over Wi-Fi and mobile data (4G/5G).

---

## 1. Architecture Overview

```
                      ┌───────────────────────────────────────────────┐
                      │             VisionNav Mobile App              │
                      │  (Flutter: Android / iOS on Wi-Fi / Cellular) │
                      └───────────────────────┬───────────────────────┘
                                              │
                              HTTPS Only (TLS Encrypted)
                              X-Session-ID + X-API-Key
                                              │
                                              ▼
                      ┌───────────────────────────────────────────────┐
                      │          Public Reverse Proxy (HTTPS)         │
                      │       (Caddy / Nginx / Cloudflare / ALB)      │
                      └───────────────────────┬───────────────────────┘
                                              │ Forward to :8000
                                              ▼
                      ┌───────────────────────────────────────────────┐
                      │           VisionNav Docker Backend            │
                      │   FastAPI + YOLOv8 + Depth Anything V2 +      │
                      │          ByteTrack + EasyOCR Metrobus         │
                      │                                               │
                      │   ┌───────────────────────────────────────┐   │
                      │   │            Session Manager            │   │
                      │   │ (Single Active Phone State Isolation) │   │
                      │   └───────────────────────────────────────┘   │
                      │                                               │
                      │   ┌───────────────────────────────────────┐   │
                      │   │    Persistent Caches & Calibration    │   │
                      │   │  /app/cache       /app/config         │   │
                      │   └───────────────────────────────────────┘   │
                      └───────────────────────────────────────────────┘
```

The Flutter app captures camera frames on the phone and transmits compressed JPEGs via HTTP multipart POST to the `/pipeline/frame` endpoint. The remotely hosted backend performs YOLOv8 obstacle detection, ByteTrack multi-object tracking, Depth Anything V2 metric distance estimation, bus route recognition, and returns structured predictions for on-device Text-to-Speech guidance.

---

## 2. Docker & Container Deployment

### 2.1 Dependencies
The container base is `python:3.10-slim`. Essential system packages required for OpenCV and container monitoring:
- `libgl1` and `libglib2.0-0`: Required by OpenCV (`cv2`) for image processing in headless Debian environments.
- `curl`: Required for Docker container health check probes.

Python packages are specified in `requirements.txt`:
```
ultralytics>=8.0.0
opencv-python>=4.8.0
fastapi>=0.100.0
uvicorn[standard]>=0.23.0
python-multipart>=0.0.6
timm>=0.9.0
transformers>=4.40.0
torch>=2.0.0
pillow>=10.0.0
easyocr>=1.7.0
```

### 2.2 Model & OCR Weight Preparation
A clean git checkout is enough. The image **does not COPY** gitignored host files (`yolov8n.pt`, `model-small.onnx`). Unused MiDaS ONNX weights are not downloaded.

During `docker build`, `tools/prepare_weights.py` fetches only the models this service loads:
- **YOLOv8n**: Ultralytics `yolov8n.pt` (~6.5 MB)
- **Depth Anything V2 Metric Indoor Small** (default, same as `pipeline/config.py`): Hugging Face id `depth-anything/Depth-Anything-V2-Metric-Indoor-Small-hf`
- **EasyOCR**: English CRAFT detector + Latin recognizer

Baked copies live in `/opt/visionnav-weights` inside the image.

```bash
python tools/prepare_weights.py
```

`.dockerignore` keeps Git history, `.env` secrets, Flutter/`visionnav_app` builds, debug media (`runs/`, images), and local `*.pt`/`*.onnx` out of the build context.

### 2.3 Persistent Caches & Storage Volumes
Compose mounts:
1. `/app/config`: geometric and depth-scale calibration JSON. Survives restarts.
2. `/app/cache`: Hugging Face, Torch, and EasyOCR caches.
3. `/app/runs`: optional debug snapshots.

A **fresh empty volume hides** files that were in the image at the same path. `docker-entrypoint.sh` runs `tools/seed_runtime_weights.py` on every start and merges missing files from baked `/opt/visionnav-weights` into the cache and config volumes. Existing volume files are never overwritten, so incomplete or older volumes are completed safely, and prepared weights remain available after restart.

### 2.4 Startup Command
Start Uvicorn with **1 worker process**:
```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 1
```
> [!IMPORTANT]
> **Why single-worker (`--workers 1`)?**
> The vision pipeline maintains heavy neural networks in memory and manages a stateful tracker (ByteTrack) and single active phone session. Multiple Uvicorn workers would duplicate multi-gigabyte models into multiple operating system processes and fragment tracking/calibration state across different workers.

### 2.5 Quickstart with Docker Compose

1. Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```
2. Configure your secret API key in `.env`:
   ```env
   VISIONNAV_API_KEY=your_secure_secret_api_key_here
   SESSION_TIMEOUT_SECONDS=30.0
   MAX_UPLOAD_SIZE_MB=10.0
   ```
3. Build and launch:
   ```bash
   docker compose up -d --build
   ```
4. Verify readiness:
   ```bash
   curl http://localhost:8000/ready
   ```

---

## 3. Lightweight Readiness & Health Checks

Remote server hosting and Docker containers run in headless environments **without physical webcams attached**. 

- **Readiness Check (`GET /ready`)**:
  - Non-blocking, instant response.
  - Minimal public response (`{"status": "ready", "api": "ok"}`).
  - Does NOT leak internal model names, file paths, or session status to unauthenticated visitors.
  - Docker uses this endpoint:
    ```dockerfile
    HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
        CMD curl -f http://localhost:8000/ready || exit 1
    ```
- **Health & Status Endpoints (`GET /health`, `/pipeline/status`, `/session/status`, `/calibrate/*status`)**:
  - All status inspection endpoints require valid authentication (`X-API-Key` or `Bearer` token).

---

## 4. Session Isolation & Anti-Mixing Architecture

### 4.1 The Shared-State Problem
The inference backend maintains state across sequential frames:
1. **ByteTrack Tracker**: Associates object bounding boxes across consecutive frames using Kalman filters and track IDs.
2. **Distance Smoother**: Applies exponential moving average (EMA) smoothing to distances keyed by `track_id`.
3. **Bus Route Stability Tracker**: Accumulates a 5-frame rolling window of OCR matches to confirm stable transit lines.
4. **Calibration Collectors**: Accumulates live ground-truth height fractions or depth estimates.

If two phones stream frames simultaneously, or if an app restarts without resetting, track IDs and smoothing histories become mixed, leading to corrupted obstacle alerts.

### 4.2 Solution: Single Active Phone Session
VisionNav explicitly supports **one active phone session initially**:
- Every client request passes an `X-Session-ID` header (or query param).
- The `SessionManager` maintains a lease with an inactivity timeout (`SESSION_TIMEOUT_SECONDS`, default 30s).
- **Session Conflict (409 Conflict)**: If Phone B attempts to stream frames or acquire a session while Phone A is actively streaming, the backend returns HTTP 409 Conflict:
  ```json
  {
    "detail": "Session conflict: Request session 'phone-B' conflicts with active session 'phone-A' (24.2s lease remaining)."
  }
  ```
- **Automatic State Reset**: Whenever a session is acquired, taken over (`force=true`), or a new phone connects after lease expiry, `pipeline.reset()`, `calibrator.reset()`, and `depth_calibrator.reset()` are invoked automatically. This clears the Kalman filter, resets smoother dictionaries, flushes OCR history, and resets frame index to 0.
- **Session Release**: When the phone app pauses, exits, or the camera screen unmounts, it invokes `POST /session/release`, returning the server to idle.

---

## 5. Security & Access Protection

1. **Explicit Production Mode Startup Refusal**:
   - In production mode (`VISIONNAV_ENV=production` or `ENVIRONMENT=production`), the backend **refuses startup and terminates immediately** if `VISIONNAV_API_KEY` is not set or empty.
2. **Loopback Port Binding in Docker Compose**:
   - `docker-compose.yml` binds port 8000 strictly to `127.0.0.1:8000:8000`. Unencrypted HTTP access from outside the host is blocked at the network interface layer.
3. **API Key Authentication**:
   - Required for all inference, frame streaming, session management, and status inspection endpoints.
   - Unauthenticated requests receive `HTTP 401 Unauthorized`.
   - Only the minimal public readiness probe (`/ready` and `/`) is exposed without authentication.
4. **Disabled Endpoints in Production**:
   - Local-camera capture (`/detect/camera`, `/pipeline/camera`) and calibration mutation endpoints (`/calibrate/start`, `/calibrate/stop`, `/calibrate/apply`, `/calibrate/reset`, `/calibrate/depth/*`) are **disabled in production mode** (`HTTP 403 Forbidden`).
5. **Pre-Multipart Request-Body Size Enforcement (Including Chunked Streams)**:
   - Total body limits are enforced at the ASGI middleware layer before `python-multipart` parsing or memory buffering occurs.
   - Evaluates `Content-Length` headers immediately, and tracks raw incoming chunks for chunked/streaming requests, terminating with `HTTP 413 Payload Too Large` if `MAX_UPLOAD_SIZE_MB` is exceeded.
6. **Pre-Allocation Image Decompression Bomb Protection**:
   - PIL `Image.open` lazy inspection checks image dimensions and total pixel count (`MAX_IMAGE_WIDTH`, `MAX_IMAGE_HEIGHT`, `MAX_IMAGE_PIXELS`) before decompressing or allocating buffers in memory.
   - **No fallback to secondary decoders**: Corrupted or oversized payloads immediately fail with `HTTP 400 Bad Request` without falling back to `cv2.imdecode`.
7. **CORS Restrictions**:
   - `ALLOWED_ORIGINS` can be locked down to specific domains or apps.

---

## 6. Production HTTPS Requirement & Reverse Proxy Setup

The Flutter app enforces that **Production backend URLs MUST start with `https://`**. Insecure plain `http://` URLs are rejected by client-side validation to prevent transmitting live camera footage and API keys unencrypted over public cellular or Wi-Fi networks.

### 6.1 Reverse Proxy Setup (Caddy - Recommended)
Caddy provides automatic, zero-config Let's Encrypt SSL certificates:
```caddy
# Caddyfile
api.visionnav.yourdomain.com {
    reverse_proxy localhost:8000 {
        header_up X-Real-IP {remote_host}
        header_up X-Forwarded-Proto https
    }
}
```

### 6.2 Reverse Proxy Setup (Nginx)
```nginx
server {
    listen 80;
    server_name api.visionnav.yourdomain.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name api.visionnav.yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/api.visionnav.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.visionnav.yourdomain.com/privkey.pem;

    client_max_body_size 10M;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

---

## 7. Hardware Sizing Estimates: CPU and RAM

These initial estimates represent baseline operational profiles for CPU-only inference:

| Component | Weight Size | Estimated RAM Footprint | CPU Processing Latency (x86_64, 4 vCPUs) |
| :--- | :--- | :--- | :--- |
| **Python Runtime + FastAPI + Uvicorn** | — | ~150 MB – 250 MB | < 2 ms |
| **YOLOv8n (Object Detection)** | 6.5 MB | ~200 MB – 350 MB | 25 ms – 45 ms |
| **ByteTrack (Object Tracking)** | — | ~30 MB – 60 MB | 5 ms – 10 ms |
| **Depth Anything V2 Metric Small (322x322)** | ~100 MB | ~900 MB – 1.4 GB | 280 ms – 480 ms |
| **EasyOCR (CRAFT + Latin Recognition)** | ~100 MB | ~350 MB – 600 MB | 350 ms – 700 ms *(runs every 6 frames only on buses)* |
| **Active Frame Buffer & Torch Tensors** | — | ~150 MB – 300 MB | — |
| **Total Operational Baseline** | **~210 MB** | **~1.8 GB – 2.9 GB** | **~350 ms – 550 ms/frame** (≈ 2–3 FPS on CPU) |

### Recommended Server Specifications
- **Minimum Instance**: 2 vCPUs, 4 GB RAM (e.g. AWS `t3.medium`, GCP `e2-standard-2`, DigitalOcean 4GB Droplet).
- **Recommended Instance**: 4 vCPUs, 8 GB RAM (e.g. AWS `c6i.xlarge` or `c7g.xlarge`, Hetzner `CPX31`).
- **GPU Instance (Optional for high throughput / >10 FPS)**: 1x NVIDIA T4 or L4 (4 vCPUs, 8 GB RAM, PyTorch CUDA). Latency drops to < 50 ms/frame.

---

## 8. What Needs Empirical Measurement

The hardware requirements above are estimates. The following metrics **cannot be assumed and must be measured under real-world conditions**:

1. **Uplink Latency over 4G/5G and Real-World Wi-Fi**:
   - Uplink bandwidth varies significantly between indoor transit hubs and streets.
   - Measure upload time for 640x480 JPEG (typically 40–80 KB) under 100 ms – 300 ms cellular RTT.
2. **End-to-End Latency vs Mobile Battery Drain**:
   - Measure the round-trip latency (Phone camera capture + JPEG compression + cellular upload + server inference + JSON response + on-device speech synthesis).
   - Target budget: < 800 ms total round-trip for responsive walking guidance.
3. **Inference Input Resolution Trade-Off**:
   - Benchmark `DEPTH_ANYTHING_INPUT_SIZE` on target host:
     - `266`: ~30% faster CPU inference, slightly lower depth edge sharpness.
     - `322`: SWEET SPOT (tested on laptop at ~500 ms).
     - `392`: ~60% slower CPU inference.
4. **Thermal Throttling & Burst CPU Limits**:
   - Cloud burstable instances (e.g. AWS `t3`/`t4g`, GCP `e2-micro`) throttle CPU when credits deplete. Sustained video streaming requires non-burstable CPU instances (e.g. `c6i`, `c7g`, dedicated vCPUs).
5. **Memory Profile Under Sustained Frame Streaming**:
   - Monitor Python / PyTorch garbage collection cycles over 30+ minutes of continuous streaming to ensure zero memory leaks.

---

## 9. Remaining Blockers & Hosting Requirements

Before public release to visually impaired users, the following blockers and operational requirements must be addressed:

1. **Production Domain & TLS Certificate**:
   - A public DNS domain or subdomain (e.g. `api.visionnav.yourdomain.com`) pointing to the server IP.
   - Valid Let's Encrypt SSL/TLS certificate configured on the reverse proxy.
2. **Firewall & Ingress Security**:
   - Port 80 and 443 open to the Internet.
   - Port 8000 closed to the public Internet (accessible only locally via reverse proxy).
3. **Mobile Network Jitter & Reconnection**:
   - Test seamless handover when the phone transitions between Wi-Fi and mobile data without dropping navigation.
4. **Multi-User Scaling (Post-Initial Deployment)**:
   - The initial design explicitly supports **one active phone session**.
   - Supporting concurrent phone sessions will require per-session pipeline instances or a worker pool architecture with session routing.
