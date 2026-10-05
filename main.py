from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from ultralytics import YOLO

import cv2
import numpy as np

from pathlib import Path



from pipeline import PipelineConfig, VisionNavPipeline

from pipeline.config import DEBUG_SNAPSHOT_DIR, DETECTION_CONF

from pipeline.camera import capture_frame

from pipeline.geometric_calibration import (
    CalibrationCollector,
    load_focal_ratio,
    save_focal_ratio,
)
from pipeline.depth_scale_calibration import (
    DepthScaleCollector,
    load_depth_scale,
    save_depth_scale,
)



app = FastAPI(title="VisionNav API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

model = YOLO("yolov8n.pt")

pipeline = VisionNavPipeline(PipelineConfig())

# Apply a previously saved per-camera geometric calibration, if present.
_saved_focal_ratio = load_focal_ratio()
if _saved_focal_ratio:
    pipeline.distance_calc.geometric.focal_ratio = _saved_focal_ratio

calibrator = CalibrationCollector()

# Apply a previously saved per-camera depth-scale correction, if present.
_saved_depth_scale = load_depth_scale()
if _saved_depth_scale:
    pipeline.distance_calc.metric_scale, pipeline.distance_calc.metric_shift = _saved_depth_scale

depth_calibrator = DepthScaleCollector()


TARGET_CLASSES = {"person", "bicycle", "car", "motorcycle", "bus", "truck"}


def decode_upload(image_bytes: bytes) -> np.ndarray | None:
    """Decode an uploaded JPEG, honouring EXIF orientation.

    Phone cameras commonly store the sensor image plus an EXIF rotation flag.
    cv2.imdecode ignores EXIF, which would rotate the scene 90 degrees and make
    bounding-box HEIGHT actually measure the object's WIDTH — breaking geometric
    distance. PIL's exif_transpose applies the rotation first.
    """
    import io

    from PIL import Image, ImageOps

    try:
        with Image.open(io.BytesIO(image_bytes)) as img:
            img = ImageOps.exif_transpose(img).convert("RGB")
            rgb = np.array(img)
        return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    except Exception:
        return cv2.imdecode(np.frombuffer(image_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)





def parse_detections(results, include_all: bool = False):

    detections = []

    for box in results.boxes:

        name = results.names[int(box.cls)]

        if not include_all and name not in TARGET_CLASSES:

            continue

        detections.append({

            "class": name,

            "confidence": round(float(box.conf), 2),

            "relevant": name in TARGET_CLASSES,

        })

    return detections





def object_to_dict(obj):

    return {

        "track_id": obj.track_id,

        "class": obj.class_name,

        "confidence": round(obj.confidence, 2),

        "estimated_distance_m": obj.estimated_distance_m,

        "distance_label": obj.distance_label,

        "is_metric": obj.is_metric,

        "bbox_xyxy": [round(v, 1) for v in obj.bbox_xyxy],

        "route_line": obj.route_line,

        "route_code": obj.route_code,

        "route_destination": obj.route_destination,

        "route_direction": obj.route_direction,

        "route_confidence": (
            None if obj.route_confidence is None else round(obj.route_confidence, 2)
        ),

        "route_is_stable": obj.route_is_stable,

        "route_tts_message": obj.route_tts_message,

    }





@app.get("/")

def home():

    return {

        "message": "VisionNav API is running",

        "endpoints": [

            "/health",

            "/docs",

            "/detect",

            "/detect/camera",

            "/pipeline/status",

            "/pipeline/camera",

            "/pipeline/frame",

        ],

    }





@app.get("/health")

def health():

    ok, frame, cam_debug = capture_frame(pipeline.config.camera_index, warmup_frames=5)

    return {

        "api": "ok",

        "yolo_model": "yolov8n.pt",

        "camera": ok,

        "camera_status": cam_debug,

        "pipeline_mode": pipeline.active_mode,

    }





@app.get("/pipeline/status")

def pipeline_status():

    return {

        "mode": pipeline.active_mode,

        "tracking_backend": pipeline.tracker.name,

        "mono_depth_backend": pipeline.mono_depth.name,

        "stereo_depth_backend": pipeline.stereo_depth.name,

        "stereo_status": pipeline.stereo_status.reason,

        "midas_active": False,

        "note": "Distances are estimated metric values — validate with MAE/RMSE before claiming accuracy.",

    }





@app.post("/detect")

async def detect(file: UploadFile = File(...)):

    image_bytes = await file.read()

    results = model.predict(source=image_bytes, conf=DETECTION_CONF, verbose=False)[0]

    detections = parse_detections(results, include_all=True)



    return {

        "filename": file.filename,

        "count": len(detections),

        "detections": detections,

    }





@app.get("/detect/camera")

def detect_camera_snapshot():

    ok, frame, cam_debug = capture_frame(

        pipeline.config.camera_index,

        warmup_frames=pipeline.config.camera_warmup_frames,

    )

    if not ok or frame is None:

        return {"error": "Could not capture frame from camera", "debug": cam_debug}



    snapshot_path = VisionNavPipeline.save_debug_snapshot(

        frame, DEBUG_SNAPSHOT_DIR / "camera_snapshot.jpg"

    )



    # Try lower threshold first; empty scene is valid but we expose debug stats.

    results = model.predict(frame, conf=DETECTION_CONF, verbose=False)[0]

    detections = parse_detections(results, include_all=True)



    if len(detections) == 0:

        # Second pass with very low conf to distinguish "nothing in view" vs broken frame.

        results_low = model.predict(frame, conf=0.1, verbose=False)[0]

        low_detections = parse_detections(results_low, include_all=True)

    else:

        low_detections = detections



    return {

        "source": "camera",

        "count": len(detections),

        "detections": detections,

        "low_conf_preview": low_detections[:5],

        "debug": {

            **cam_debug,

            "snapshot_saved": snapshot_path,

            "hint": "count=0 usually means nothing detected in view; check snapshot image",

        },

    }





@app.get("/pipeline/camera")

def pipeline_camera_snapshot():

    result, frame, cam_debug = pipeline.process_camera_snapshot()

    if result is None or frame is None:

        return {"error": "Could not capture frame from camera", "debug": cam_debug}



    snapshot_path = VisionNavPipeline.save_debug_snapshot(

        frame, DEBUG_SNAPSHOT_DIR / "pipeline_snapshot.jpg"

    )



    return {

        "frame_index": result.frame_index,

        "mode": result.mode,

        "depth_backend": result.depth_backend,

        "tracking_backend": result.tracking_backend,

        "count": len(result.objects),

        "objects": [object_to_dict(o) for o in result.objects],

        "formatted_output": result.format_lines(),

        "debug": {**result.debug, "snapshot_saved": snapshot_path},

    }



def _frame_result_payload(result):
    return {
        "frame_index": result.frame_index,
        "mode": result.mode,
        "depth_backend": result.depth_backend,
        "tracking_backend": result.tracking_backend,
        "count": len(result.objects),
        "objects": [object_to_dict(o) for o in result.objects],
        "formatted_output": result.format_lines(),
        "debug": result.debug,
    }


@app.post("/pipeline/frame")
async def pipeline_frame(file: UploadFile = File(...)):
    image_bytes = await file.read()
    decoded = decode_upload(image_bytes)
    if decoded is None:
        raise HTTPException(status_code=400, detail="Could not decode uploaded image")

    result = pipeline.process_frame(decoded)

    # Feed any running calibration session with this frame's bbox fractions.
    fractions = pipeline.distance_calc.last_height_fractions
    truncated = pipeline.distance_calc.last_truncated
    if calibrator.active is not None:
        for obj in result.objects:
            frac = fractions.get(obj.track_id)
            if frac is not None:
                calibrator.feed(obj.class_name, frac, truncated.get(obj.track_id, False))

    # Feed any running depth-scale session with the UNcorrected model depth of
    # the largest matching object (the person standing at the tape-measured spot).
    if depth_calibrator.active is not None:
        target = depth_calibrator.active.target_class
        candidates = [o for o in result.objects if o.class_name == target and o.raw_depth_value > 0]
        if candidates:
            largest = max(
                candidates,
                key=lambda o: (o.bbox_xyxy[2] - o.bbox_xyxy[0]) * (o.bbox_xyxy[3] - o.bbox_xyxy[1]),
            )
            depth_calibrator.feed(largest.class_name, largest.raw_depth_value)

    payload = _frame_result_payload(result)
    payload["debug"] = {
        **payload.get("debug", {}),
        "frame_height_px": int(decoded.shape[0]),
        "frame_width_px": int(decoded.shape[1]),
        "geometric_focal_ratio": pipeline.distance_calc.geometric.focal_ratio,
        "height_fractions": {str(k): round(v, 4) for k, v in fractions.items()},
        "truncated": {str(k): v for k, v in truncated.items()},
        "calibrating": calibrator.active is not None,
        "calibration_samples": calibrator.active.count if calibrator.active else 0,
        "depth_scale": pipeline.distance_calc.metric_scale,
        "depth_shift": pipeline.distance_calc.metric_shift,
        "depth_calibrating": depth_calibrator.active is not None,
        "depth_calibration_samples": depth_calibrator.active.count if depth_calibrator.active else 0,
    }
    return payload


# ── Per-camera geometric calibration (drive these from a browser) ────────────

@app.get("/calibrate/start")
def calibrate_start(distance: float, height: float = 1.70, target: str = "person"):
    """Begin collecting bbox height fractions at a KNOWN distance in metres."""
    if distance <= 0 or height <= 0:
        raise HTTPException(status_code=400, detail="distance and height must be > 0")
    calibrator.start(distance_m=distance, object_height_m=height, target_class=target)
    return {
        "status": "collecting",
        "distance_m": distance,
        "object_height_m": height,
        "target_class": target,
        "instructions": (
            f"Keep the {target} FULLY in frame at {distance} m while the app streams "
            "frames, then open /calibrate/stop"
        ),
    }


@app.get("/calibrate/stop")
def calibrate_stop():
    """Finish the current point and compute its focal ratio."""
    return calibrator.stop()


@app.get("/calibrate/status")
def calibrate_status():
    active = calibrator.active
    return {
        "active": active is not None,
        "current_distance_m": active.distance_m if active else None,
        "samples": active.count if active else 0,
        "rejected_truncated": active.rejected_truncated if active else 0,
        "points_collected": len(calibrator.points),
        "points": calibrator.points,
        "focal_ratio_in_use": pipeline.distance_calc.geometric.focal_ratio,
    }


@app.get("/calibrate/apply")
def calibrate_apply():
    """Average all collected points, apply live, and persist to JSON."""
    fit = calibrator.fit()
    if "error" in fit:
        return fit

    focal_ratio = fit["focal_ratio"]
    pipeline.distance_calc.geometric.focal_ratio = focal_ratio
    saved_to = save_focal_ratio(
        focal_ratio,
        meta={
            "num_points": fit["num_points"],
            "focal_ratio_std": round(fit["focal_ratio_std"], 5),
            "points": fit["points"],
            "source": "phone_camera_via_/pipeline/frame",
        },
    )
    return {
        "status": "applied",
        "focal_ratio": round(focal_ratio, 5),
        "focal_ratio_std": round(fit["focal_ratio_std"], 5),
        "num_points": fit["num_points"],
        "saved_to": saved_to,
        "note": "Applied live — no restart needed. Distances now use this value.",
    }


@app.get("/calibrate/reset")
def calibrate_reset():
    calibrator.reset()
    return {"status": "reset", "points_collected": 0}


# ── Per-camera DEPTH-MODEL scale calibration (drive these from a browser) ────
# Corrects the systematic scale error of Depth Anything V2 Metric for THIS phone:
#     corrected_m = scale * predicted_m + shift
# Collect 3-5 points at tape-measured distances (e.g. 1, 2, 3, 4, 5 m), then apply.

@app.get("/calibrate/depth/start")
def calibrate_depth_start(distance: float, target: str = "person"):
    """Begin collecting the model's raw distance for a `target` standing at `distance` m."""
    if distance <= 0:
        raise HTTPException(status_code=400, detail="distance must be > 0")
    depth_calibrator.start(distance_m=distance, target_class=target)
    return {
        "status": "collecting",
        "distance_m": distance,
        "target_class": target,
        "instructions": (
            f"Point the phone at the {target} standing exactly {distance} m away, keep the "
            "Vision tab streaming for ~5 s, then open /calibrate/depth/stop"
        ),
    }


@app.get("/calibrate/depth/stop")
def calibrate_depth_stop():
    """Finish the current point (median of the raw predictions at that distance)."""
    return depth_calibrator.stop()


@app.get("/calibrate/depth/status")
def calibrate_depth_status():
    active = depth_calibrator.active
    return {
        "active": active is not None,
        "current_distance_m": active.distance_m if active else None,
        "samples": active.count if active else 0,
        "points_collected": len(depth_calibrator.points),
        "points": depth_calibrator.points,
        "scale_in_use": pipeline.distance_calc.metric_scale,
        "shift_in_use": pipeline.distance_calc.metric_shift,
    }


@app.get("/calibrate/depth/apply")
def calibrate_depth_apply():
    """Fit scale/shift over all points, apply live, persist to JSON, report MAE/RMSE."""
    fit = depth_calibrator.fit()
    if "error" in fit:
        return fit

    pipeline.distance_calc.metric_scale = fit["scale"]
    pipeline.distance_calc.metric_shift = fit["shift"]
    saved_to = save_depth_scale(
        fit["scale"],
        fit["shift"],
        meta={
            "mode": fit["mode"],
            "num_points": fit["num_points"],
            "mae_before_m": round(fit["mae_before_m"], 4),
            "mae_after_m": round(fit["mae_after_m"], 4),
            "rmse_before_m": round(fit["rmse_before_m"], 4),
            "rmse_after_m": round(fit["rmse_after_m"], 4),
            "depth_model": pipeline.config.depth_anything_model,
            "points": fit["points"],
            "source": "phone_camera_via_/pipeline/frame",
        },
    )
    return {
        "status": "applied",
        "scale": round(fit["scale"], 5),
        "shift": round(fit["shift"], 5),
        "mode": fit["mode"],
        "num_points": fit["num_points"],
        "mae_before_m": round(fit["mae_before_m"], 3),
        "mae_after_m": round(fit["mae_after_m"], 3),
        "rmse_before_m": round(fit["rmse_before_m"], 3),
        "rmse_after_m": round(fit["rmse_after_m"], 3),
        "points": fit["points"],
        "saved_to": saved_to,
        "note": "Applied live — no restart needed. Reloaded automatically on future starts.",
    }


@app.get("/calibrate/depth/reset")
def calibrate_depth_reset():
    """Discard collected points AND revert to the uncorrected model output."""
    depth_calibrator.reset()
    pipeline.distance_calc.metric_scale = 1.0
    pipeline.distance_calc.metric_shift = 0.0
    return {"status": "reset", "scale": 1.0, "shift": 0.0, "points_collected": 0}


