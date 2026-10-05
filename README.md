# VisionNav: Assistive Navigation System for Visually Impaired Persons

VisionNav is an intelligent, multi-modal assistive navigation system designed to help visually impaired individuals navigate their environments safely. By combining real-time computer vision, object tracking, depth estimation, and planned integrations for text recognition (OCR) and localization (GPS), VisionNav acts as a comprehensive sensor-to-feedback pipeline.

The system dynamically adapts to the available hardware, utilising a **dual-camera stereo setup** for high-precision physical depth triangulation when calibrated, and automatically falling back to a **monocular camera setup** powered by state-of-the-art transformer-based depth models.

---

## 🚀 Features & Tech Stack

### 👁️ Computer Vision & Tracking
* **Object Detection**: **YOLOv8** (Ultralytics) for high-frequency detection of critical obstacle classes (`person`, `car`, `bus`, `truck`).
* **Multi-Object Tracking**: **ByteTrack** (default) and **DeepSORT** (under implementation) to maintain temporal identity across frames, allowing the system to track velocity and predict potential collisions.

### 📐 Depth & Distance Estimation
* **Stereo Depth (High Precision)**: Uses OpenCV **Stereo SGBM** or **RAFT-Stereo** when a calibrated stereo camera pair is detected. Triangulates physical distances using camera focal length and baseline distance.
* **Monocular Fallback (Zero-Shot)**: Leverages **Depth-Anything-V2** or **Metric3D** models to predict dense depth maps from a single camera feed when stereo calibration is unavailable.
* **Temporal Smoothing**: Exponential Moving Average (EMA) filtering on estimated distances to prevent depth jitter and provide stable audio/visual feedback cues.

### 📍 GPS & Spatial Localization (Planned Integration)
* Outdoor coordinate tracking and path navigation mapping.
* Dynamic route planning and destination guidance using GPS sensor modules.

### 📝 Bus route reading
* **EasyOCR** reads destination text on a detected bus. ByteTrack keeps the bus identity, and a route is announced only after the same route agrees in 3 of the last 5 reads.
* Islamabad **Green Line**, **Orange Line**, and the **feeder** corridors from the October 2026 metro-status snapshot are in the route database. Feeder recognition, the missing stop lists, and how to try a real bus photo are described in [docs/bus_route_recognition.md](docs/bus_route_recognition.md).
* The phone speaks the sentence produced by the backend. Mocked tests do not measure accuracy on real buses.

### ⚡ Infrastructure
* **FastAPI & Uvicorn**: Lightweight, asynchronous web API exposing endpoints for single image processing, camera status, and active pipeline orchestration.
* **OpenCV**: Handles webcam capture, stereo image rectification, and visual debug overlays.

---

## 📂 Project Structure

```
VisionNav/
├── config/
│   └── stereo_calibration.example.json  # Reference configuration for stereo setups
├── pipeline/
│   ├── depth/                           # Depth estimation backends (DepthAnythingV2, Metric3D)
│   ├── stereo/                          # Stereo camera depth estimation (SGBM, RAFT)
│   ├── tracking/                        # Object tracking implementations (ByteTrack)
│   ├── distance/                        # Distance calculations and smoothing
│   ├── camera.py                        # OpenCV camera capture and diagnostics
│   ├── orchestrator.py                  # Main pipeline runner (VisionNavPipeline)
│   └── config.py                        # Pipeline configuration variables
├── runs/
│   └── debug/                           # Diagnostic snapshots and output visuals
├── main.py                              # FastAPI web application entrypoint
├── run_pipeline.py                      # CLI-based execution script (webcam/images)
├── verify_setup.py                      # Environment verification utility
├── requirements.txt                     # Python packages list
└── .gitignore                           # Git exclusion rules
```

---

## 🛠️ Setup & Installation

### 1. Clone the Repository
```bash
git clone https://github.com/AbdullahAziz01/VisionNav.git
cd VisionNav
```

### 2. Create a Virtual Environment
Create and activate a virtual environment to keep dependencies isolated:
```bash
# Windows
python -m venv venv
venv\Scripts\activate

# Linux / macOS
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Dependencies
Install all required libraries listed in `requirements.txt`:
```bash
pip install -r requirements.txt
```
> **Note**: For GPU acceleration (highly recommended for real-time inference), ensure you have [CUDA Toolkit](https://developer.nvidia.com/cuda-downloads) installed and the corresponding PyTorch build.

### 4. Verify Environment Setup
VisionNav includes a verification utility to confirm your environment, project files, and camera access are configured correctly:
```bash
python verify_setup.py
```

---

## 💻 Usage

VisionNav can be run as a terminal-based CLI application or as a hosted web API.

### 1. Command Line Interface (CLI)
Run the pipeline in real-time using your webcam:
```bash
python run_pipeline.py
```

To run the pipeline on a single test image:
```bash
python run_pipeline.py test.jpg
```
* **Controls**: Press `Q` while focusing on the window to exit.

### 2. FastAPI Web Server
Start the backend API using Uvicorn:
```bash
uvicorn main:app --reload
```
Once the server is running, access the interactive API docs at:
👉 **[http://localhost:8000/docs](http://localhost:8000/docs)**

#### Available Endpoints:
* `GET /health`: Diagnoses camera connectivity, active model weights, and pipeline fallback status.
* `GET /pipeline/status`: Exposes current active backends (monocular fallback model vs stereo calibration).
* `POST /detect`: Receives an uploaded image and returns a JSON payload of classes, confidence scores, and bounding boxes.
* `GET /pipeline/camera`: Captures a frame from the live camera, processes it through the entire tracking and depth estimation pipeline, saves a debug snapshot, and returns estimated physical distances.

---

## 📊 Calibration & Evaluation

* **Stereo Calibration**: To use high-precision stereo depth estimation, perform camera calibration and save your calibration coefficients (focal length, baseline, rectification matrix) to `config/stereo_calibration.json`. Refer to `config/stereo_calibration.example.json` for details.
* **Accuracy Logging**: The pipeline evaluates estimated distance vs actual ground truth and logs performance metrics into `metrics.csv` to track Mean Absolute Error (MAE) and Root Mean Squared Error (RMSE) across runs.
