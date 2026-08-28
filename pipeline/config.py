"""VisionNav pipeline configuration."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

# Detection / tracking
YOLO_MODEL = "yolov8n.pt"
DETECTION_CONF = 0.25
TRACKER_BACKEND = "bytetrack"  # swap to "deepsort" when implemented
TARGET_CLASSES = {"bus", "person", "car", "truck"}

# Depth backend selection (monocular fallback)
# Options: "depth_anything_v2", "metric3d"
MONO_DEPTH_BACKEND = "depth_anything_v2"
# Use a metric-capable variant when available; relative-only models need scale calibration.
#DEPTH_ANYTHING_MODEL = "depth-anything/Depth-Anything-V2-Metric-Outdoor-Small-hf"
DEPTH_ANYTHING_MODEL = "depth-anything/Depth-Anything-V2-Metric-Indoor-Small-hf"

METRIC3D_CHECKPOINT = ""  # TODO: path to Metric3D weights for mobile deployment

# Stereo backend selection when a valid calibrated pair is detected
# Options: "stereo_sgbm", "raft_stereo"
STEREO_DEPTH_BACKEND = "stereo_sgbm"
STEREO_CALIBRATION_PATH = Path("config/stereo_calibration.json")

# Camera
CAMERA_INDEX = 0
CAMERA_WARMUP_FRAMES = 15

# Distance estimation
BBOX_DEPTH_SAMPLE = "center_region"  # median inside central 50% of bbox
TEMPORAL_SMOOTHING_ALPHA = 0.35  # EMA: higher = more responsive, lower = smoother
RELATIVE_DEPTH_SCALE_M = 20.0  # TODO: replace with calibrated scale; not validated ground truth
MIN_VALID_DEPTH_M = 0.5
MAX_VALID_DEPTH_M = 80.0

# Output
DEBUG_SNAPSHOT_DIR = Path("runs/debug")

@dataclass
class PipelineConfig:
    yolo_model: str = YOLO_MODEL
    detection_conf: float = DETECTION_CONF
    tracker_backend: str = TRACKER_BACKEND
    target_classes: set[str] = field(default_factory=lambda: set(TARGET_CLASSES))
    mono_depth_backend: str = MONO_DEPTH_BACKEND
    depth_anything_model: str = DEPTH_ANYTHING_MODEL
    metric3d_checkpoint: str = METRIC3D_CHECKPOINT
    stereo_depth_backend: str = STEREO_DEPTH_BACKEND
    stereo_calibration_path: Path = STEREO_CALIBRATION_PATH
    camera_index: int = CAMERA_INDEX
    camera_warmup_frames: int = CAMERA_WARMUP_FRAMES
    temporal_smoothing_alpha: float = TEMPORAL_SMOOTHING_ALPHA
    relative_depth_scale_m: float = RELATIVE_DEPTH_SCALE_M
