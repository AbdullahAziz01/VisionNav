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
# Options: "depth_anything_v2", "metric3d", "midas_onnx"
#   depth_anything_v2 (Metric variant) -> per-pixel depth in METRES, no per-camera
#       calibration needed, works when obstacles are partially in frame / very close.
#       This is the active backend.
#   midas_onnx -> RELATIVE depth only (not metres). Kept for comparison/benchmarks.
MONO_DEPTH_BACKEND = "depth_anything_v2"

# Depth Anything V2 Metric comes in two variants trained for different scenes.
# Pick the one matching where you are TESTING right now:
#   "indoor"  -> rooms, corridors, home testing (max ~20 m)
#   "outdoor" -> streets, bus stands, open air (max ~80 m)
DEPTH_ANYTHING_ENVIRONMENT = "indoor"
_DEPTH_ANYTHING_MODELS = {
    "indoor": "depth-anything/Depth-Anything-V2-Metric-Indoor-Small-hf",
    "outdoor": "depth-anything/Depth-Anything-V2-Metric-Outdoor-Small-hf",
}
DEPTH_ANYTHING_MODEL = _DEPTH_ANYTHING_MODELS[DEPTH_ANYTHING_ENVIRONMENT]
# Network input size (multiple of 14). Measured on this laptop CPU (640x480 frame):
#   518 -> 2.4 s/frame (model default) | 392 -> 0.84 s | 322 -> 0.51 s | 266 -> 0.32 s
# Depth values stayed within ~5% across sizes; 322 is the speed/accuracy sweet spot.
DEPTH_ANYTHING_INPUT_SIZE = 322
DEPTH_ANYTHING_THREADS = 4  # torch CPU threads (0 = torch default)

METRIC3D_CHECKPOINT = ""  # TODO: path to Metric3D weights for mobile deployment

# MiDaS ONNX options
MIDAS_ONNX_MODEL_PATH = "model-small.onnx"
MIDAS_ONNX_SCALE = 1.0   # Modular calibration scale (disparity modifier)
MIDAS_ONNX_SHIFT = 0.0   # Modular calibration shift (disparity modifier)
# ORT CPU thread settings — 0 = let ORT choose automatically
MIDAS_ONNX_INTRA_OP_THREADS = 4
MIDAS_ONNX_INTER_OP_THREADS = 1

# Staggered depth processing: compute depth every N frames, YOLO runs every frame.
# 1 = synchronous (depth every frame); 2+ = staggered mode.
DEPTH_COMPUTATION_INTERVAL = 1

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
RELATIVE_DEPTH_SCALE_M = 1000.0  # Provisional scale; replace with calibrated value (Z = scale / disparity)
MIN_VALID_DEPTH_M = 0.5
MAX_VALID_DEPTH_M = 80.0

# ── Geometric (pinhole) distance for KNOWN-SIZE classes — OPTIONAL refinement ─
# Pinhole model (resolution-independent form):
#     Z = real_height_m * GEOMETRIC_FOCAL_RATIO / (bbox_height_px / image_height_px)
# It is only valid when the FULL object (a person head-to-toe) is inside the frame
# and GEOMETRIC_FOCAL_RATIO has been calibrated for the *phone* camera.
# For the VisionNav use case (obstacles often cut off / very close) the metric depth
# model above is the primary source, so this is DISABLED by default. When enabled it
# is only applied to fully-visible objects and blended with the depth-model value.
USE_GEOMETRIC_DISTANCE = False
GEOMETRIC_FOCAL_RATIO = 1.2720  # Laptop webcam value — NOT valid for the phone camera
# Assumed real-world heights in metres per class (rough averages).
OBJECT_REAL_HEIGHTS_M = {
    "person": 1.70,
    "bicycle": 1.10,
    "motorcycle": 1.10,
    "car": 1.50,
    "bus": 3.20,
    "truck": 3.50,
}

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
    depth_anything_input_size: int = DEPTH_ANYTHING_INPUT_SIZE
    depth_anything_threads: int = DEPTH_ANYTHING_THREADS
    metric3d_checkpoint: str = METRIC3D_CHECKPOINT
    midas_onnx_model_path: str = MIDAS_ONNX_MODEL_PATH
    midas_onnx_scale: float = MIDAS_ONNX_SCALE
    midas_onnx_shift: float = MIDAS_ONNX_SHIFT
    midas_onnx_intra_op_threads: int = MIDAS_ONNX_INTRA_OP_THREADS
    midas_onnx_inter_op_threads: int = MIDAS_ONNX_INTER_OP_THREADS
    depth_computation_interval: int = DEPTH_COMPUTATION_INTERVAL
    stereo_depth_backend: str = STEREO_DEPTH_BACKEND
    stereo_calibration_path: Path = STEREO_CALIBRATION_PATH
    camera_index: int = CAMERA_INDEX
    camera_warmup_frames: int = CAMERA_WARMUP_FRAMES
    temporal_smoothing_alpha: float = TEMPORAL_SMOOTHING_ALPHA
    relative_depth_scale_m: float = RELATIVE_DEPTH_SCALE_M
    use_geometric_distance: bool = USE_GEOMETRIC_DISTANCE
    geometric_focal_ratio: float = GEOMETRIC_FOCAL_RATIO
    object_real_heights_m: dict = field(default_factory=lambda: dict(OBJECT_REAL_HEIGHTS_M))
