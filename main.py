import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, File, Header, HTTPException, Request, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import Response
import pydantic
from ultralytics import YOLO
import cv2
import numpy as np

from pipeline import PipelineConfig, VisionNavPipeline
from pipeline.config import DEBUG_SNAPSHOT_DIR, DETECTION_CONF
from pipeline.camera import capture_frame
from pipeline.session_manager import SessionManager
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

# ── Deployment & Security Configuration ───────────────────────────────────────
ENV = os.environ.get("VISIONNAV_ENV", os.environ.get("ENVIRONMENT", "development")).strip().lower()
IS_PRODUCTION = ENV == "production"

API_KEY = os.environ.get("VISIONNAV_API_KEY", "").strip()
MAX_UPLOAD_SIZE_MB = float(os.environ.get("MAX_UPLOAD_SIZE_MB", "10.0"))
MAX_UPLOAD_SIZE_BYTES = int(MAX_UPLOAD_SIZE_MB * 1024 * 1024)
MAX_IMAGE_WIDTH = int(os.environ.get("MAX_IMAGE_WIDTH", "4096"))
MAX_IMAGE_HEIGHT = int(os.environ.get("MAX_IMAGE_HEIGHT", "4096"))
MAX_IMAGE_PIXELS = int(os.environ.get("MAX_IMAGE_PIXELS", str(1920 * 1080 * 4)))  # ~8.3M pixels

_origins_raw = os.environ.get("ALLOWED_ORIGINS", "*").strip()
ALLOWED_ORIGINS = [o.strip() for o in _origins_raw.split(",") if o.strip()] or ["*"]


VALID_ENVIRONMENTS = {"development", "production", "test", "testing"}


def validate_startup_configuration():
    """Validate environment name, non-empty API key in production, and positive upload limits."""
    env_str = ENV.strip().lower()
    if env_str not in VALID_ENVIRONMENTS:
        raise ValueError(
            f"Invalid environment '{ENV}'. VISIONNAV_ENV must be one of: {sorted(list(VALID_ENVIRONMENTS))}"
        )

    if IS_PRODUCTION:
        if not API_KEY or not API_KEY.strip():
            raise RuntimeError(
                "FATAL: Production mode (VISIONNAV_ENV=production) refuses startup without a configured "
                "nonempty VISIONNAV_API_KEY. Configure a strong API key in environment variables."
            )

    if MAX_UPLOAD_SIZE_MB <= 0:
        raise ValueError(f"MAX_UPLOAD_SIZE_MB must be positive (got {MAX_UPLOAD_SIZE_MB})")
    if MAX_IMAGE_WIDTH <= 0:
        raise ValueError(f"MAX_IMAGE_WIDTH must be positive (got {MAX_IMAGE_WIDTH})")
    if MAX_IMAGE_HEIGHT <= 0:
        raise ValueError(f"MAX_IMAGE_HEIGHT must be positive (got {MAX_IMAGE_HEIGHT})")
    if MAX_IMAGE_PIXELS <= 0:
        raise ValueError(f"MAX_IMAGE_PIXELS must be positive (got {MAX_IMAGE_PIXELS})")


validate_startup_configuration()

_models_ready = False


def initialize_and_warm_models():
    """Initialize and warm the configured YOLO, depth, and OCR models during application startup.

    Fails startup if required weights cannot load.
    """
    # 1. Warm YOLO
    try:
        dummy = np.zeros((320, 320, 3), dtype=np.uint8)
        _ = model.predict(dummy, conf=DETECTION_CONF, verbose=False)
    except Exception as e:
        raise RuntimeError(
            f"FATAL: Failed to load and warm YOLO model ({pipeline.config.yolo_model}): {e}"
        ) from e

    # 2. Warm Depth Model
    try:
        if hasattr(pipeline.mono_depth, "_load"):
            pipeline.mono_depth._load()
        _ = pipeline.mono_depth.estimate(dummy)
    except Exception as e:
        raise RuntimeError(
            f"FATAL: Failed to load and warm mono depth model ({pipeline.mono_depth.name}): {e}"
        ) from e

    # 3. Warm OCR Model
    try:
        reader = pipeline.bus_routes.reader._ensure_reader()
        dummy_crop = np.zeros((60, 160, 3), dtype=np.uint8)
        _ = reader.readtext(dummy_crop)
    except Exception as e:
        raise RuntimeError(f"FATAL: Failed to load and warm OCR model: {e}") from e


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _models_ready
    validate_startup_configuration()
    initialize_and_warm_models()
    _models_ready = True
    try:
        yield
    finally:
        _models_ready = False


# ── ASGI Request Body Size Limiter Middleware ────────────────────────────────

class BodySizeExceededError(StarletteHTTPException):
    def __init__(self, detail: str):
        super().__init__(status_code=413, detail=detail)


class RequestBodyLimitMiddleware:
    """Enforce total request-body limits before multipart parsing, including chunked uploads.

    Aborts reading and returns 413 immediately when Content-Length or stream chunks
    exceed the configured threshold, preventing memory exhaustion attacks.
    """

    def __init__(self, app, max_bytes_getter):
        self.app = app
        self.max_bytes_getter = max_bytes_getter

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        max_bytes = self.max_bytes_getter()

        # Check Content-Length header if present before reading any body bytes
        headers = dict(scope.get("headers", []))
        content_length_raw = headers.get(b"content-length")
        if content_length_raw:
            try:
                content_length = int(content_length_raw)
                if content_length > max_bytes:
                    response = Response(
                        content=json.dumps(
                            {"detail": f"Request body exceeds limit of {max_bytes} bytes"}
                        ),
                        status_code=413,
                        media_type="application/json",
                    )
                    await response(scope, receive, send)
                    return
            except ValueError:
                pass

        total_bytes = 0
        response_started = False

        async def limited_receive():
            nonlocal total_bytes
            message = await receive()
            if message["type"] == "http.request":
                chunk = message.get("body", b"")
                total_bytes += len(chunk)
                if total_bytes > max_bytes:
                    raise BodySizeExceededError(
                        f"Request body exceeds limit of {max_bytes} bytes"
                    )
            return message

        async def tracking_send(message):
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracking_send)
        except BodySizeExceededError as exc:
            if not response_started:
                response = Response(
                    content=json.dumps({"detail": exc.detail}),
                    status_code=413,
                    media_type="application/json",
                )
                await response(scope, receive, send)
                return
            raise


app = FastAPI(
    title="VisionNav API",
    description="Vision inference backend for mobile vision and obstacle navigation.",
    version="1.0.0",
    lifespan=lifespan,
)

# Request body limit runs before routing/multipart parsing
app.add_middleware(
    RequestBodyLimitMiddleware,
    max_bytes_getter=lambda: MAX_UPLOAD_SIZE_BYTES,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

model = YOLO("yolov8n.pt")
pipeline = VisionNavPipeline(PipelineConfig())
session_manager = SessionManager()

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


# ── Security & Mode Helpers ──────────────────────────────────────────────────

async def verify_api_key(
    request: Request,
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
) -> Optional[str]:
    """Verify backend access protection when an API key is configured.

    If VISIONNAV_API_KEY is unset/empty and not in production, open access is allowed.
    If set, requests must provide matching X-API-Key or Authorization Bearer header.
    """
    if not API_KEY:
        if IS_PRODUCTION:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Production mode requires authentication.",
            )
        return None

    auth_header = request.headers.get("Authorization", "")
    bearer_token = None
    if auth_header.startswith("Bearer "):
        bearer_token = auth_header[7:].strip()

    client_key = x_api_key or bearer_token
    if not client_key or client_key != API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key. Provide a valid X-API-Key header or Bearer token.",
        )
    return client_key


def require_not_production():
    """Disable hardware webcam and calibration mutation endpoints in production."""
    if IS_PRODUCTION:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Endpoint disabled in production mode.",
        )


async def read_uploaded_file(file: UploadFile, max_bytes: Optional[int] = None) -> bytes:
    """Read an uploaded file in chunks with strict payload size limit enforcement."""
    limit = MAX_UPLOAD_SIZE_BYTES if max_bytes is None else max_bytes
    content_length = file.headers.get("content-length")
    if content_length and int(content_length) > limit:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Uploaded file exceeds limit of {MAX_UPLOAD_SIZE_MB:.1f} MB",
        )

    chunks: list[bytes] = []
    total = 0
    chunk_size = 1024 * 1024  # 1 MB chunk
    while True:
        chunk = await file.read(chunk_size)
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"Uploaded file exceeds limit of {MAX_UPLOAD_SIZE_MB:.1f} MB",
            )
        chunks.append(chunk)

    return b"".join(chunks)


def _do_state_reset():
    """Reset all temporal pipeline, calibration, and depth-calibration state.

    Must be called while the processing guard is held so that no inference
    can run concurrently with the reset.
    """
    pipeline.reset()
    calibrator.reset()
    depth_calibrator.reset()


def _validate_session_access(session_id: Optional[str]) -> bool:
    """Validate that the session matches the active phone session.

    In production mode, requests without an explicit X-Session-ID are
    rejected even when no session is active.
    """
    allowed, reason, reset_needed = session_manager.validate_or_auto_acquire(
        session_id, require_explicit=IS_PRODUCTION,
    )
    if not allowed:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=reason)
    if reset_needed:
        _do_state_reset()
    return True


# ── Request / Response Schemas ───────────────────────────────────────────────

class SessionAcquireRequest(pydantic.BaseModel):
    session_id: str
    force: bool = False
    device_info: Optional[str] = None


class SessionReleaseRequest(pydantic.BaseModel):
    session_id: str


# ── Frame decoding & object formatting ───────────────────────────────────────

def decode_upload(image_bytes: bytes) -> np.ndarray:
    """Decode an uploaded image, honouring EXIF orientation and rejecting oversized images

    BEFORE full buffer allocation, without falling back to another decoder.
    """
    import io
    from PIL import Image, ImageOps

    if not image_bytes:
        raise ValueError("Empty image payload")

    try:
        with Image.open(io.BytesIO(image_bytes)) as img:
            fmt = img.format
            if fmt not in ("JPEG", "PNG", "WEBP", "MPO"):
                raise ValueError(f"Unsupported image format: {fmt}")

            w, h = img.size
            if w <= 0 or h <= 0:
                raise ValueError("Invalid image dimensions (<= 0)")
            if w > MAX_IMAGE_WIDTH or h > MAX_IMAGE_HEIGHT or (w * h) > MAX_IMAGE_PIXELS:
                raise ValueError(
                    f"Image dimensions {w}x{h} ({w*h} pixels) exceed maximum allowed limit "
                    f"({MAX_IMAGE_WIDTH}x{MAX_IMAGE_HEIGHT}, max {MAX_IMAGE_PIXELS} pixels)"
                )

            transposed = ImageOps.exif_transpose(img)
            tw, th = transposed.size
            if tw > MAX_IMAGE_WIDTH or th > MAX_IMAGE_HEIGHT or (tw * th) > MAX_IMAGE_PIXELS:
                raise ValueError(
                    f"Transposed image dimensions {tw}x{th} exceed maximum allowed limit"
                )

            rgb = transposed.convert("RGB")
            arr = np.array(rgb)
            return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
    except Exception as e:
        raise ValueError(f"Image decode failed: {e}") from e


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


# ── System / Health / Readiness Endpoints ────────────────────────────────────

@app.get("/")
def home():
    """Minimal root endpoint."""
    return {
        "status": "ready",
        "api": "ok",
    }


@app.get("/ready")
def readiness_check():
    """Minimal non-blocking public readiness probe for containers and load balancers.

    Returns HTTP 200 once initialization completes; HTTP 503 while initializing.
    Never runs inference or accesses hardware cameras.
    """
    if not _models_ready:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service initializing: models not ready",
        )
    return {
        "status": "ready",
        "api": "ok",
    }


@app.get("/health")
def health(_: Optional[str] = Depends(verify_api_key)):
    """Health check endpoint. Requires authentication."""
    cam_ok = False
    cam_debug = {"status": "unattached", "hint": "No hardware camera (hosted remote server mode)"}
    try:
        ok, frame, debug = capture_frame(pipeline.config.camera_index, warmup_frames=1)
        if ok:
            cam_ok = True
            cam_debug = debug
    except Exception:
        pass

    return {
        "api": "ok",
        "yolo_model": "yolov8n.pt",
        "camera": cam_ok,
        "camera_status": cam_debug,
        "pipeline_mode": pipeline.active_mode,
        "session": session_manager.status(),
    }


@app.get("/pipeline/status")
def pipeline_status(_: Optional[str] = Depends(verify_api_key)):
    """Authenticated pipeline status check."""
    return {
        "mode": pipeline.active_mode,
        "tracking_backend": pipeline.tracker.name,
        "mono_depth_backend": pipeline.mono_depth.name,
        "stereo_depth_backend": pipeline.stereo_depth.name,
        "stereo_status": pipeline.stereo_status.reason,
        "midas_active": False,
        "session": session_manager.status(),
        "note": "Distances are estimated metric values — validate with MAE/RMSE before claiming accuracy.",
    }


# ── Session Management Endpoints ─────────────────────────────────────────────

@app.post("/session/acquire")
@app.post("/session/start")
def session_acquire(req: SessionAcquireRequest, _: Optional[str] = Depends(verify_api_key)):
    """Acquire the single active phone session.

    Holds the processing guard during acquire+reset so that a takeover
    cannot overlap with an in-flight inference pass.
    """
    with session_manager.processing_guard(timeout=5.0) as acquired:
        if not acquired:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cannot acquire session: a frame is currently being processed. Retry shortly.",
            )

        success, msg, details = session_manager.acquire_session(
            session_id=req.session_id,
            force=req.force,
            device_info=req.device_info,
        )
        if not success:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=msg)

        if details.get("was_reset_needed"):
            _do_state_reset()

        return {
            "status": "acquired",
            "message": msg,
            "session": session_manager.status(),
        }


@app.post("/session/release")
def session_release(req: SessionReleaseRequest, _: Optional[str] = Depends(verify_api_key)):
    """Explicitly release the phone session and reset state.

    Holds the processing guard during release+reset so that a release
    cannot overlap with in-flight inference.
    """
    with session_manager.processing_guard(timeout=5.0) as acquired:
        if not acquired:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cannot release session: a frame is currently being processed. Retry shortly.",
            )

        released = session_manager.release_session(req.session_id)
        if released:
            _do_state_reset()
            return {"status": "released", "session_id": req.session_id}
        return {"status": "not_active", "session_id": req.session_id}


@app.get("/session/status")
def session_status(_: Optional[str] = Depends(verify_api_key)):
    """Authenticated check for the current active session."""
    return session_manager.status()


# ── Inference Endpoints ──────────────────────────────────────────────────────

@app.post("/detect")
async def detect(
    file: UploadFile = File(...),
    _: Optional[str] = Depends(verify_api_key),
):
    image_bytes = await read_uploaded_file(file)
    try:
        decoded = decode_upload(image_bytes)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    with session_manager.processing_guard(timeout=5.0) as acquired:
        if not acquired:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A frame or pipeline task is currently being processed. Wait for it to complete.",
            )
        results = model.predict(source=decoded, conf=DETECTION_CONF, verbose=False)[0]
        detections = parse_detections(results, include_all=True)

    return {
        "filename": file.filename,
        "count": len(detections),
        "detections": detections,
    }


@app.get("/detect/camera")
def detect_camera_snapshot(
    _: Optional[str] = Depends(verify_api_key),
    _not_prod: None = Depends(require_not_production),
):
    with session_manager.processing_guard(timeout=5.0) as acquired:
        if not acquired:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A frame or pipeline task is currently being processed. Wait for it to complete.",
            )

        ok, frame, cam_debug = capture_frame(
            pipeline.config.camera_index,
            warmup_frames=pipeline.config.camera_warmup_frames,
        )
        if not ok or frame is None:
            return {"error": "Could not capture frame from camera", "debug": cam_debug}

        snapshot_path = VisionNavPipeline.save_debug_snapshot(
            frame, DEBUG_SNAPSHOT_DIR / "camera_snapshot.jpg"
        )

        results = model.predict(frame, conf=DETECTION_CONF, verbose=False)[0]
        detections = parse_detections(results, include_all=True)

        if len(detections) == 0:
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
def pipeline_camera_snapshot(
    _: Optional[str] = Depends(verify_api_key),
    _not_prod: None = Depends(require_not_production),
):
    with session_manager.processing_guard(timeout=5.0) as acquired:
        if not acquired:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A frame or pipeline task is currently being processed. Wait for it to complete.",
            )

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


@app.post("/pipeline/frame")
async def pipeline_frame(
    file: UploadFile = File(...),
    x_session_id: Optional[str] = Header(None, alias="X-Session-ID"),
    session_id: Optional[str] = None,
    _: Optional[str] = Depends(verify_api_key),
):
    """Process an uploaded camera frame from the active phone session.

    Enforces session isolation to prevent different phones from mixing tracking
    and distance smoothing state.  A shared processing guard rejects overlapping
    frame requests, prevents resets during inference, and refreshes the session
    lease after processing completes and before releasing the lock.
    """
    effective_session = x_session_id or session_id

    # ── Acquire the processing guard (non-blocking) ──────────────────────
    with session_manager.processing_guard(blocking=False) as acquired:
        if not acquired:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A frame is already being processed. Wait for it to complete before sending the next frame.",
            )

        # Session validation happens *inside* the guard so that any state
        # reset is serialised with inference.
        _validate_session_access(effective_session)

        image_bytes = await read_uploaded_file(file)
        try:
            decoded = decode_upload(image_bytes)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

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
        # the largest matching object.
        if depth_calibrator.active is not None:
            target = depth_calibrator.active.target_class
            candidates = [o for o in result.objects if o.class_name == target and o.raw_depth_value > 0]
            if candidates:
                largest = max(
                    candidates,
                    key=lambda o: (o.bbox_xyxy[2] - o.bbox_xyxy[0]) * (o.bbox_xyxy[3] - o.bbox_xyxy[1]),
                )
                depth_calibrator.feed(largest.class_name, largest.raw_depth_value)

        # ── Refresh the lease after frame processing and before unlocking ────
        session_manager.refresh_lease(effective_session or "")

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
            "session_id": session_manager.active_session_id,
        }
        return payload


# ── Per-camera geometric calibration ─────────────────────────────────────────

@app.get("/calibrate/start")
def calibrate_start(
    distance: float,
    height: float = 1.70,
    target: str = "person",
    x_session_id: Optional[str] = Header(None, alias="X-Session-ID"),
    session_id: Optional[str] = None,
    _: Optional[str] = Depends(verify_api_key),
    _not_prod: None = Depends(require_not_production),
):
    """Begin collecting bbox height fractions at a KNOWN distance in metres."""
    with session_manager.processing_guard(timeout=5.0) as acquired:
        if not acquired:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A frame or pipeline task is currently being processed. Wait for it to complete.",
            )
        _validate_session_access(x_session_id or session_id)
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
def calibrate_stop(
    x_session_id: Optional[str] = Header(None, alias="X-Session-ID"),
    session_id: Optional[str] = None,
    _: Optional[str] = Depends(verify_api_key),
    _not_prod: None = Depends(require_not_production),
):
    """Finish the current point and compute its focal ratio."""
    with session_manager.processing_guard(timeout=5.0) as acquired:
        if not acquired:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A frame or pipeline task is currently being processed. Wait for it to complete.",
            )
        _validate_session_access(x_session_id or session_id)
        return calibrator.stop()


@app.get("/calibrate/status")
def calibrate_status(_: Optional[str] = Depends(verify_api_key)):
    """Authenticated check for geometric calibration collector status."""
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
def calibrate_apply(
    x_session_id: Optional[str] = Header(None, alias="X-Session-ID"),
    session_id: Optional[str] = None,
    _: Optional[str] = Depends(verify_api_key),
    _not_prod: None = Depends(require_not_production),
):
    """Average all collected points, apply live, and persist to JSON."""
    with session_manager.processing_guard(timeout=5.0) as acquired:
        if not acquired:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A frame or pipeline task is currently being processed. Wait for it to complete.",
            )
        _validate_session_access(x_session_id or session_id)
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
def calibrate_reset(
    x_session_id: Optional[str] = Header(None, alias="X-Session-ID"),
    session_id: Optional[str] = None,
    _: Optional[str] = Depends(verify_api_key),
    _not_prod: None = Depends(require_not_production),
):
    with session_manager.processing_guard(timeout=5.0) as acquired:
        if not acquired:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A frame or pipeline task is currently being processed. Wait for it to complete.",
            )
        _validate_session_access(x_session_id or session_id)
        calibrator.reset()
    return {"status": "reset", "points_collected": 0}


# ── Per-camera DEPTH-MODEL scale calibration ─────────────────────────────────

@app.get("/calibrate/depth/start")
def calibrate_depth_start(
    distance: float,
    target: str = "person",
    x_session_id: Optional[str] = Header(None, alias="X-Session-ID"),
    session_id: Optional[str] = None,
    _: Optional[str] = Depends(verify_api_key),
    _not_prod: None = Depends(require_not_production),
):
    """Begin collecting the model's raw distance for a `target` standing at `distance` m."""
    with session_manager.processing_guard(timeout=5.0) as acquired:
        if not acquired:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A frame or pipeline task is currently being processed. Wait for it to complete.",
            )
        _validate_session_access(x_session_id or session_id)
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
def calibrate_depth_stop(
    x_session_id: Optional[str] = Header(None, alias="X-Session-ID"),
    session_id: Optional[str] = None,
    _: Optional[str] = Depends(verify_api_key),
    _not_prod: None = Depends(require_not_production),
):
    """Finish the current point (median of the raw predictions at that distance)."""
    with session_manager.processing_guard(timeout=5.0) as acquired:
        if not acquired:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A frame or pipeline task is currently being processed. Wait for it to complete.",
            )
        _validate_session_access(x_session_id or session_id)
        return depth_calibrator.stop()


@app.get("/calibrate/depth/status")
def calibrate_depth_status(_: Optional[str] = Depends(verify_api_key)):
    """Authenticated check for depth scale calibration collector status."""
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
def calibrate_depth_apply(
    x_session_id: Optional[str] = Header(None, alias="X-Session-ID"),
    session_id: Optional[str] = None,
    _: Optional[str] = Depends(verify_api_key),
    _not_prod: None = Depends(require_not_production),
):
    """Fit scale/shift over all points, apply live, persist to JSON, report MAE/RMSE."""
    with session_manager.processing_guard(timeout=5.0) as acquired:
        if not acquired:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A frame or pipeline task is currently being processed. Wait for it to complete.",
            )
        _validate_session_access(x_session_id or session_id)
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
def calibrate_depth_reset(
    x_session_id: Optional[str] = Header(None, alias="X-Session-ID"),
    session_id: Optional[str] = None,
    _: Optional[str] = Depends(verify_api_key),
    _not_prod: None = Depends(require_not_production),
):
    """Discard collected points AND revert to the uncorrected model output."""
    with session_manager.processing_guard(timeout=5.0) as acquired:
        if not acquired:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A frame or pipeline task is currently being processed. Wait for it to complete.",
            )
        _validate_session_access(x_session_id or session_id)
        depth_calibrator.reset()
        pipeline.distance_calc.metric_scale = 1.0
        pipeline.distance_calc.metric_shift = 0.0
    return {"status": "reset", "scale": 1.0, "shift": 0.0, "points_collected": 0}
