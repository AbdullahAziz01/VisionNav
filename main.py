from fastapi import FastAPI, File, UploadFile

from ultralytics import YOLO

import cv2

from pathlib import Path



from pipeline import PipelineConfig, VisionNavPipeline

from pipeline.config import DEBUG_SNAPSHOT_DIR, DETECTION_CONF

from pipeline.camera import capture_frame



app = FastAPI(title="VisionNav API")

model = YOLO("yolov8n.pt")

pipeline = VisionNavPipeline(PipelineConfig())



TARGET_CLASSES = {"bus", "person", "car", "truck"}





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


