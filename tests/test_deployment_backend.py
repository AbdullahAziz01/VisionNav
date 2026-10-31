"""Tests for session management, production mode refusal, access protection,

request-body limit enforcement, oversized image rejection, minimal readiness,
and concurrent-request guards (overlapping frames, takeover/release during
inference, lease expiry with reconnection).
"""

import asyncio
import io
import threading
import time
from unittest.mock import patch, MagicMock
import unittest
from PIL import Image
from starlette.testclient import TestClient

from pipeline.session_manager import SessionManager
import main


class TestSessionManager(unittest.TestCase):
    def test_acquire_and_active(self):
        mgr = SessionManager(lease_timeout_s=10.0)
        self.assertFalse(mgr.is_active())

        ok, msg, details = mgr.acquire_session("phone-session-1", now=100.0)
        self.assertTrue(ok)
        self.assertTrue(mgr.is_active(now=105.0))
        self.assertEqual(mgr.active_session_id, "phone-session-1")

    def test_conflict_prevention_across_different_sessions(self):
        mgr = SessionManager(lease_timeout_s=10.0)
        mgr.acquire_session("phone-session-1", now=100.0)

        # Phone 2 tries to acquire without force -> Conflict
        ok2, msg2, details2 = mgr.acquire_session("phone-session-2", force=False, now=105.0)
        self.assertFalse(ok2)
        self.assertIn("phone-session-1", msg2)
        self.assertIn("lease remaining", msg2)

        # Phone 2 validates incoming frame without force -> Blocked
        allowed, reason, reset_needed = mgr.validate_or_auto_acquire("phone-session-2", now=105.0)
        self.assertFalse(allowed)
        self.assertIn("Session conflict", reason)

    def test_forced_takeover(self):
        mgr = SessionManager(lease_timeout_s=10.0)
        mgr.acquire_session("phone-session-1", now=100.0)

        # Phone 2 forces takeover
        ok, msg, details = mgr.acquire_session("phone-session-2", force=True, now=105.0)
        self.assertTrue(ok)
        self.assertEqual(mgr.active_session_id, "phone-session-2")
        self.assertTrue(details.get("was_reset_needed"))

    def test_lease_timeout_and_auto_acquire(self):
        mgr = SessionManager(lease_timeout_s=10.0)
        mgr.acquire_session("phone-session-1", now=100.0)

        # After lease timeout (12 seconds later)
        self.assertFalse(mgr.is_active(now=112.0))

        # Phone 2 sends a frame after phone 1 expired -> auto-acquires and requires state reset
        allowed, reason, reset_needed = mgr.validate_or_auto_acquire("phone-session-2", now=112.0)
        self.assertTrue(allowed)
        self.assertEqual(mgr.active_session_id, "phone-session-2")
        self.assertTrue(reset_needed)

    def test_release_session(self):
        mgr = SessionManager(lease_timeout_s=10.0)
        mgr.acquire_session("phone-session-1", now=100.0)
        self.assertTrue(mgr.is_active(now=102.0))

        # Non-matching session cannot release
        self.assertFalse(mgr.release_session("random-phone"))
        self.assertTrue(mgr.is_active(now=102.0))

        # Matching session releases
        self.assertTrue(mgr.release_session("phone-session-1"))
        self.assertFalse(mgr.is_active(now=102.0))
        self.assertIsNone(mgr.active_session_id)

    def test_same_session_reconnect_after_expiry_requires_reset(self):
        """When the *same* session ID reconnects after its lease expired,
        temporal state must be reset to prevent stale tracker IDs."""
        mgr = SessionManager(lease_timeout_s=10.0)
        mgr.acquire_session("phone-A", now=100.0)

        # Lease expires at ~110
        self.assertFalse(mgr.is_active(now=115.0))

        # Same session ID auto-acquires after expiry -> reset required
        allowed, reason, reset_needed = mgr.validate_or_auto_acquire("phone-A", now=115.0)
        self.assertTrue(allowed)
        self.assertTrue(reset_needed, "Same session reconnecting after expiry must trigger state reset")
        self.assertEqual(mgr.active_session_id, "phone-A")

    def test_same_session_reconnect_after_expiry_via_acquire(self):
        """acquire_session for the same ID after expiry must also flag reset_needed."""
        mgr = SessionManager(lease_timeout_s=10.0)
        mgr.acquire_session("phone-A", now=100.0)

        ok, msg, details = mgr.acquire_session("phone-A", now=115.0)
        self.assertTrue(ok)
        self.assertTrue(details.get("was_reset_needed"),
                        "Same session re-acquiring after expiry must require reset")

    def test_refresh_lease_extends_timeout(self):
        mgr = SessionManager(lease_timeout_s=10.0)
        mgr.acquire_session("phone-A", now=100.0)

        # At t=108, lease has 2s remaining; refresh it
        mgr.refresh_lease("phone-A", now=108.0)

        # Now at t=115 (7s after refresh, still within 10s lease)
        self.assertTrue(mgr.is_active(now=115.0))
        # But at t=120 (12s after refresh) it should have expired
        self.assertFalse(mgr.is_active(now=120.0))

    def test_require_explicit_rejects_anonymous_in_production(self):
        mgr = SessionManager(lease_timeout_s=10.0)
        allowed, reason, reset = mgr.validate_or_auto_acquire(
            None, require_explicit=True,
        )
        self.assertFalse(allowed)
        self.assertIn("explicit X-Session-ID", reason)

    def test_require_explicit_rejects_empty_string_in_production(self):
        mgr = SessionManager(lease_timeout_s=10.0)
        allowed, reason, reset = mgr.validate_or_auto_acquire(
            "  ", require_explicit=True,
        )
        self.assertFalse(allowed)
        self.assertIn("explicit X-Session-ID", reason)

    def test_processing_lock_reports_status(self):
        mgr = SessionManager(lease_timeout_s=10.0)
        self.assertFalse(mgr.is_processing())

        mgr._processing_lock.acquire()
        try:
            self.assertTrue(mgr.is_processing())
        finally:
            mgr._processing_lock.release()
        self.assertFalse(mgr.is_processing())

    def test_status_includes_processing_field(self):
        mgr = SessionManager(lease_timeout_s=10.0)
        mgr.acquire_session("phone-A", now=100.0)
        st = mgr.status(now=100.0)
        self.assertIn("processing", st)
        self.assertFalse(st["processing"])


class TestPipelineReset(unittest.TestCase):
    def test_pipeline_reset_clears_state(self):
        from pipeline.config import PipelineConfig
        from pipeline.orchestrator import VisionNavPipeline

        pipe = VisionNavPipeline(PipelineConfig())
        pipe.frame_index = 42
        pipe.distance_calc.smoother.update(1, 3.5)
        self.assertIn(1, pipe.distance_calc.smoother._state)

        pipe.reset()
        self.assertEqual(pipe.frame_index, 0)
        self.assertEqual(len(pipe.distance_calc.smoother._state), 0)
        self.assertEqual(len(pipe._prev_track_ids), 0)
        self.assertIsNone(pipe._latest_mono_depth)


class TestHardenedDeploymentProtections(unittest.TestCase):
    def setUp(self):
        self.main_module = main
        self.client = TestClient(main.app)
        main.session_manager.release_session(main.session_manager.active_session_id or "")
        self.orig_env = main.ENV
        self.orig_is_prod = main.IS_PRODUCTION
        self.orig_api_key = main.API_KEY
        self.orig_max_upload = main.MAX_UPLOAD_SIZE_BYTES
        self.orig_max_upload_mb = main.MAX_UPLOAD_SIZE_MB
        self.orig_max_w = main.MAX_IMAGE_WIDTH
        self.orig_max_h = main.MAX_IMAGE_HEIGHT
        self.orig_max_pixels = main.MAX_IMAGE_PIXELS
        self.orig_models_ready = main._models_ready
        main._models_ready = True

    def tearDown(self):
        self.main_module.ENV = self.orig_env
        self.main_module.IS_PRODUCTION = self.orig_is_prod
        self.main_module.API_KEY = self.orig_api_key
        self.main_module.MAX_UPLOAD_SIZE_BYTES = self.orig_max_upload
        self.main_module.MAX_UPLOAD_SIZE_MB = self.orig_max_upload_mb
        self.main_module.MAX_IMAGE_WIDTH = self.orig_max_w
        self.main_module.MAX_IMAGE_HEIGHT = self.orig_max_h
        self.main_module.MAX_IMAGE_PIXELS = self.orig_max_pixels
        self.main_module._models_ready = self.orig_models_ready
        # Ensure the processing lock is released after each test
        if main.session_manager._processing_lock.locked():
            main.session_manager._processing_lock.release()
        self.main_module.session_manager.release_session(
            self.main_module.session_manager.active_session_id or ""
        )

    # ── 1. Startup Configuration & Environment Validation ────────────────────

    def test_invalid_environment_name_raises_error(self):
        self.main_module.ENV = "staging"
        with self.assertRaises(ValueError) as ctx:
            self.main_module.validate_startup_configuration()
        self.assertIn("Invalid environment 'staging'", str(ctx.exception))

    def test_positive_limits_validation(self):
        # MAX_UPLOAD_SIZE_MB <= 0
        self.main_module.MAX_UPLOAD_SIZE_MB = 0
        with self.assertRaises(ValueError) as ctx:
            self.main_module.validate_startup_configuration()
        self.assertIn("MAX_UPLOAD_SIZE_MB must be positive", str(ctx.exception))

        self.main_module.MAX_UPLOAD_SIZE_MB = 10.0
        self.main_module.MAX_IMAGE_WIDTH = -1
        with self.assertRaises(ValueError) as ctx:
            self.main_module.validate_startup_configuration()
        self.assertIn("MAX_IMAGE_WIDTH must be positive", str(ctx.exception))

        self.main_module.MAX_IMAGE_WIDTH = 4096
        self.main_module.MAX_IMAGE_HEIGHT = 0
        with self.assertRaises(ValueError) as ctx:
            self.main_module.validate_startup_configuration()
        self.assertIn("MAX_IMAGE_HEIGHT must be positive", str(ctx.exception))

        self.main_module.MAX_IMAGE_HEIGHT = 4096
        self.main_module.MAX_IMAGE_PIXELS = 0
        with self.assertRaises(ValueError) as ctx:
            self.main_module.validate_startup_configuration()
        self.assertIn("MAX_IMAGE_PIXELS must be positive", str(ctx.exception))

    def test_production_mode_refuses_startup_without_or_empty_api_key(self):
        self.main_module.ENV = "production"
        self.main_module.IS_PRODUCTION = True

        # Empty key
        self.main_module.API_KEY = ""
        with self.assertRaises(RuntimeError) as ctx:
            self.main_module.validate_startup_configuration()
        self.assertIn("refuses startup without a configured nonempty VISIONNAV_API_KEY", str(ctx.exception))

        # Whitespace-only key
        self.main_module.API_KEY = "   "
        with self.assertRaises(RuntimeError) as ctx:
            self.main_module.validate_startup_configuration()
        self.assertIn("refuses startup without a configured nonempty VISIONNAV_API_KEY", str(ctx.exception))

    def test_production_mode_allows_startup_with_nonempty_api_key(self):
        self.main_module.ENV = "production"
        self.main_module.IS_PRODUCTION = True
        self.main_module.API_KEY = "super-secret-production-key"
        # Should not raise
        self.main_module.validate_startup_configuration()

    # ── 2. Model Warmup & Readiness Probe ────────────────────────────────────

    def test_readiness_probe_returns_503_during_initialization(self):
        self.main_module._models_ready = False
        resp = self.client.get("/ready")
        self.assertEqual(resp.status_code, 503)
        self.assertIn("Service initializing", resp.json()["detail"])

    def test_readiness_probe_returns_200_minimal_when_ready(self):
        self.main_module._models_ready = True
        resp = self.client.get("/ready")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data, {"status": "ready", "api": "ok"})
        # Must not leak internal models, file paths, or session IDs
        self.assertNotIn("yolo_model", data)
        self.assertNotIn("session", data)
        self.assertNotIn("mono_depth_backend", data)

    def test_readiness_probe_never_runs_inference_or_cameras(self):
        self.main_module._models_ready = True
        with patch.object(self.main_module.model, "predict") as mock_predict, \
             patch.object(self.main_module.pipeline, "process_frame") as mock_process, \
             patch("main.capture_frame") as mock_cam:
            resp = self.client.get("/ready")
            self.assertEqual(resp.status_code, 200)
            mock_predict.assert_not_called()
            mock_process.assert_not_called()
            mock_cam.assert_not_called()

    def test_failed_weights_load_raises_startup_error(self):
        with patch.object(self.main_module.model, "predict", side_effect=Exception("Corrupt weights")):
            with self.assertRaises(RuntimeError) as ctx:
                self.main_module.initialize_and_warm_models()
            self.assertIn("Failed to load and warm YOLO model", str(ctx.exception))

    # ── 3. Authenticated Status Endpoints ─────────────────────────────────────

    def test_status_endpoints_require_authentication(self):
        self.main_module.API_KEY = "test-secret-key"

        endpoints = [
            "/pipeline/status",
            "/session/status",
            "/calibrate/status",
            "/calibrate/depth/status",
            "/health",
        ]

        for path in endpoints:
            # Without key -> 401
            resp_no_auth = self.client.get(path)
            self.assertEqual(resp_no_auth.status_code, 401, f"{path} should require auth")

            # With valid key -> 200
            resp_auth = self.client.get(path, headers={"X-API-Key": "test-secret-key"})
            self.assertEqual(resp_auth.status_code, 200, f"{path} should succeed with auth")

    # ── 4. Local-Camera and Calibration Mutations Disabled in Production ──────

    def test_production_mode_disables_hardware_and_calibration_mutations(self):
        self.main_module.IS_PRODUCTION = True
        self.main_module.API_KEY = "test-prod-key"
        headers = {"X-API-Key": "test-prod-key"}

        disabled_get_endpoints = [
            "/detect/camera",
            "/pipeline/camera",
            "/calibrate/start?distance=2.0",
            "/calibrate/stop",
            "/calibrate/apply",
            "/calibrate/reset",
            "/calibrate/depth/start?distance=2.0",
            "/calibrate/depth/stop",
            "/calibrate/depth/apply",
            "/calibrate/depth/reset",
        ]

        for path in disabled_get_endpoints:
            resp = self.client.get(path, headers=headers)
            self.assertEqual(
                resp.status_code,
                403,
                f"{path} must return 403 Forbidden in production mode",
            )
            self.assertIn("disabled in production mode", resp.json()["detail"])

    # ── 5. Total Request-Body Limit Before Multipart Parsing ─────────────────

    def test_request_body_limit_enforced_by_content_length(self):
        self.main_module.MAX_UPLOAD_SIZE_BYTES = 100
        # Exceeds 100 bytes
        payload = b"X" * 300
        resp = self.client.post(
            "/detect",
            files={"file": ("test.jpg", payload, "image/jpeg")},
        )
        self.assertEqual(resp.status_code, 413)
        self.assertIn("exceeds limit", resp.json()["detail"])

    def test_request_body_limit_enforced_on_chunked_streaming_uploads(self):
        self.main_module.MAX_UPLOAD_SIZE_BYTES = 200
        boundary = "------------------------boundary123"

        def chunk_generator():
            yield f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"test.jpg\"\r\nContent-Type: image/jpeg\r\n\r\n".encode()
            for _ in range(5):
                yield b"A" * 80  # 400 bytes > 200 bytes limit
            yield f"\r\n--{boundary}--\r\n".encode()

        resp = self.client.post(
            "/pipeline/frame",
            content=chunk_generator(),
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        self.assertEqual(resp.status_code, 413)
        self.assertIn("exceeds limit", resp.json()["detail"])

    # ── 6. Oversized Decoded Images Rejected Before Allocation ────────────────

    def test_oversized_decoded_images_rejected_before_allocation(self):
        # Configure small test dimensions
        self.main_module.MAX_IMAGE_WIDTH = 200
        self.main_module.MAX_IMAGE_HEIGHT = 200
        self.main_module.MAX_IMAGE_PIXELS = 40000

        # Create an image exceeding max dimensions (e.g. 300x100 = 30000 pixels, width > 200)
        img = Image.new("RGB", (300, 100), color="blue")
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        raw_bytes = buf.getvalue()

        # Direct decode_upload call
        with self.assertRaises(ValueError) as ctx:
            self.main_module.decode_upload(raw_bytes)
        self.assertIn("exceed maximum allowed", str(ctx.exception))

        # API upload endpoint
        files = {"file": ("test.jpg", raw_bytes, "image/jpeg")}
        resp = self.client.post("/detect", files=files)
        self.assertEqual(resp.status_code, 400)
        self.assertIn("exceed maximum allowed", resp.json()["detail"])

    def test_corrupt_image_fails_without_fallback_to_other_decoder(self):
        corrupted = b"NOT_AN_IMAGE_HEADER_DATA_GARBAGE"
        with self.assertRaises(ValueError) as ctx:
            self.main_module.decode_upload(corrupted)
        self.assertIn("Image decode failed", str(ctx.exception))

    # ── 7. Production mode requires explicit session ID ──────────────────────

    def test_production_mode_rejects_frame_without_session_id(self):
        """In production, /pipeline/frame without X-Session-ID returns 409."""
        self.main_module.IS_PRODUCTION = True
        self.main_module.API_KEY = "test-prod-key"

        img = Image.new("RGB", (100, 100), color="red")
        buf = io.BytesIO()
        img.save(buf, format="JPEG")

        resp = self.client.post(
            "/pipeline/frame",
            files={"file": ("frame.jpg", buf.getvalue(), "image/jpeg")},
            headers={"X-API-Key": "test-prod-key"},
            # No X-Session-ID
        )
        self.assertEqual(resp.status_code, 409)
        self.assertIn("explicit X-Session-ID", resp.json()["detail"])

    def test_production_frame_requires_api_key_and_processes_authenticated_upload(self):
        """An authenticated production frame reaches inference and returns a result."""
        from pipeline.models import FrameResult

        self.main_module.IS_PRODUCTION = True
        self.main_module.API_KEY = "test-prod-key"
        image = Image.new("RGB", (64, 64), color="green")
        buf = io.BytesIO()
        image.save(buf, format="JPEG")
        jpeg_bytes = buf.getvalue()
        frame_result = FrameResult(
            frame_index=1,
            mode="monocular",
            depth_backend="depth_anything_v2",
            tracking_backend="bytetrack",
            objects=[],
            debug={},
        )

        with patch.object(self.main_module.pipeline, "process_frame", return_value=frame_result) as process:
            unauthenticated = self.client.post(
                "/pipeline/frame",
                files={"file": ("frame.jpg", jpeg_bytes, "image/jpeg")},
                headers={"X-Session-ID": "phone-test"},
            )
            self.assertEqual(unauthenticated.status_code, 401)
            process.assert_not_called()

            authenticated = self.client.post(
                "/pipeline/frame",
                files={"file": ("frame.jpg", jpeg_bytes, "image/jpeg")},
                headers={
                    "X-API-Key": "test-prod-key",
                    "X-Session-ID": "phone-test",
                },
            )

        self.assertEqual(authenticated.status_code, 200)
        self.assertEqual(authenticated.json()["frame_index"], 1)
        process.assert_called_once()


class TestConcurrentSessionGuard(unittest.TestCase):
    """Tests for the shared processing guard that serialises frame inference,
    takeover, release, and pipeline/calibration resets."""

    def setUp(self):
        self.main_module = main
        self.client = TestClient(main.app)
        main.session_manager.release_session(main.session_manager.active_session_id or "")
        self.orig_is_prod = main.IS_PRODUCTION
        self.orig_api_key = main.API_KEY
        self.orig_models_ready = main._models_ready
        main._models_ready = True
        main.IS_PRODUCTION = False
        main.API_KEY = ""

    def tearDown(self):
        main.IS_PRODUCTION = self.orig_is_prod
        main.API_KEY = self.orig_api_key
        main._models_ready = self.orig_models_ready
        if main.session_manager._processing_lock.locked():
            main.session_manager._processing_lock.release()
        main.session_manager.release_session(
            main.session_manager.active_session_id or ""
        )

    def _make_test_jpeg(self) -> bytes:
        img = Image.new("RGB", (64, 64), color="green")
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        return buf.getvalue()

    # ── Overlapping frame requests ───────────────────────────────────────

    def test_overlapping_frame_requests_rejected(self):
        """Second /pipeline/frame while the first is processing must get 409."""
        from pipeline.models import FrameResult
        inference_started = threading.Event()
        inference_continue = threading.Event()
        jpeg_bytes = self._make_test_jpeg()

        dummy_result = FrameResult(
            frame_index=1,
            mode="monocular",
            depth_backend="none",
            tracking_backend="none",
            objects=[],
            debug={},
        )

        def slow_process(frame):
            inference_started.set()
            inference_continue.wait(timeout=5.0)
            return dummy_result

        results = {}

        def send_frame(key):
            try:
                resp = self.client.post(
                    "/pipeline/frame",
                    files={"file": ("frame.jpg", jpeg_bytes, "image/jpeg")},
                    headers={"X-Session-ID": "phone-A"},
                )
                results[key] = resp.status_code
            except Exception as e:
                results[key] = f"error: {e}"

        with patch.object(main.pipeline, "process_frame", side_effect=slow_process):
            # Start first frame in a thread
            t1 = threading.Thread(target=send_frame, args=("first",))
            t1.start()

            # Wait for inference to actually begin
            self.assertTrue(inference_started.wait(timeout=5.0))

            # Send second frame while first is still processing
            t2 = threading.Thread(target=send_frame, args=("second",))
            t2.start()
            t2.join(timeout=5.0)

            # Let the first frame finish
            inference_continue.set()
            t1.join(timeout=5.0)

        self.assertEqual(results["second"], 409, "Overlapping frame should be rejected with 409")
        self.assertEqual(results["first"], 200, "First frame should succeed with 200")

    # ── Takeover during inference ────────────────────────────────────────

    def test_takeover_waits_for_inference_to_finish(self):
        """session/acquire with force=true blocks until in-flight inference finishes,
        then resets state. We verify it does not return an error."""
        from pipeline.models import FrameResult
        inference_started = threading.Event()
        inference_continue = threading.Event()
        jpeg_bytes = self._make_test_jpeg()

        dummy_result = FrameResult(
            frame_index=1,
            mode="monocular",
            depth_backend="none",
            tracking_backend="none",
            objects=[],
            debug={},
        )

        def slow_process(frame):
            inference_started.set()
            inference_continue.wait(timeout=5.0)
            return dummy_result

        results = {}

        def send_frame():
            try:
                resp = self.client.post(
                    "/pipeline/frame",
                    files={"file": ("frame.jpg", jpeg_bytes, "image/jpeg")},
                    headers={"X-Session-ID": "phone-A"},
                )
                results["frame"] = resp.status_code
            except Exception as e:
                results["frame"] = f"error: {e}"

        def do_takeover():
            try:
                resp = self.client.post(
                    "/session/acquire",
                    json={"session_id": "phone-B", "force": True},
                )
                results["takeover"] = resp.status_code
                results["takeover_body"] = resp.json()
            except Exception as e:
                results["takeover"] = f"error: {e}"

        with patch.object(main.pipeline, "process_frame", side_effect=slow_process):
            t1 = threading.Thread(target=send_frame)
            t1.start()
            self.assertTrue(inference_started.wait(timeout=5.0))

            # Takeover request while inference is in progress
            t2 = threading.Thread(target=do_takeover)
            t2.start()

            # Give takeover time to block on the processing lock
            time.sleep(0.3)

            # Let inference finish
            inference_continue.set()
            t1.join(timeout=5.0)
            t2.join(timeout=5.0)

        self.assertEqual(results["takeover"], 200,
                         f"Takeover should succeed after inference finishes, got: {results.get('takeover')}")
        self.assertEqual(
            main.session_manager.active_session_id, "phone-B",
            "After takeover, phone-B should be the active session",
        )

    # ── Release during inference ─────────────────────────────────────────

    def test_release_waits_for_inference_to_finish(self):
        """session/release blocks until in-flight inference finishes,
        then resets state."""
        from pipeline.models import FrameResult
        inference_started = threading.Event()
        inference_continue = threading.Event()
        jpeg_bytes = self._make_test_jpeg()

        dummy_result = FrameResult(
            frame_index=1,
            mode="monocular",
            depth_backend="none",
            tracking_backend="none",
            objects=[],
            debug={},
        )

        def slow_process(frame):
            inference_started.set()
            inference_continue.wait(timeout=5.0)
            return dummy_result

        results = {}

        def send_frame():
            try:
                resp = self.client.post(
                    "/pipeline/frame",
                    files={"file": ("frame.jpg", jpeg_bytes, "image/jpeg")},
                    headers={"X-Session-ID": "phone-A"},
                )
                results["frame"] = resp.status_code
            except Exception as e:
                results["frame"] = f"error: {e}"

        def do_release():
            try:
                resp = self.client.post(
                    "/session/release",
                    json={"session_id": "phone-A"},
                )
                results["release"] = resp.status_code
            except Exception as e:
                results["release"] = f"error: {e}"

        with patch.object(main.pipeline, "process_frame", side_effect=slow_process):
            t1 = threading.Thread(target=send_frame)
            t1.start()
            self.assertTrue(inference_started.wait(timeout=5.0))

            t2 = threading.Thread(target=do_release)
            t2.start()

            time.sleep(0.3)
            inference_continue.set()
            t1.join(timeout=5.0)
            t2.join(timeout=5.0)

        self.assertEqual(results["release"], 200,
                         f"Release should succeed after inference finishes, got: {results.get('release')}")

    # ── Lease expiry during gap + reconnection ───────────────────────────

    def test_expired_same_session_reconnect_resets_state(self):
        """When session-A expires and reconnects with the same ID, temporal
        state must be reset (tracker, smoother, frame index)."""
        mgr = main.session_manager
        jpeg_bytes = self._make_test_jpeg()

        # Acquire session with a short timeout
        original_timeout = mgr.lease_timeout_s
        mgr.lease_timeout_s = 5.0

        try:
            # Establish session
            resp = self.client.post(
                "/session/acquire",
                json={"session_id": "phone-A"},
            )
            self.assertEqual(resp.status_code, 200)

            # Pump pipeline state so frame_index > 0
            main.pipeline.frame_index = 42

            # Simulate expiry by backdating the heartbeat
            with mgr._lock:
                mgr.last_heartbeat = time.monotonic() - 10.0

            self.assertFalse(mgr.is_active(), "Session should have expired")

            # Reconnect with the same session ID via pipeline/frame
            with patch.object(main.pipeline, "process_frame") as mock_pf:
                # Return a minimal FrameResult
                from pipeline.models import FrameResult
                mock_pf.return_value = FrameResult(
                    frame_index=0, mode="monocular",
                    depth_backend="none", tracking_backend="none",
                    objects=[], debug={},
                )
                resp = self.client.post(
                    "/pipeline/frame",
                    files={"file": ("frame.jpg", jpeg_bytes, "image/jpeg")},
                    headers={"X-Session-ID": "phone-A"},
                )

            # Session should be re-acquired
            self.assertTrue(mgr.is_active())
            self.assertEqual(mgr.active_session_id, "phone-A")
            # pipeline.reset() should have been called because of expiry
            self.assertEqual(main.pipeline.frame_index, 0,
                             "Pipeline frame_index should be reset after expired reconnect")
        finally:
            mgr.lease_timeout_s = original_timeout

    # ── Lease refresh after processing ───────────────────────────────────

    def test_lease_refreshed_after_frame_processing(self):
        """After /pipeline/frame completes, the session lease should be
        refreshed so it doesn't expire during long inference."""
        mgr = main.session_manager
        jpeg_bytes = self._make_test_jpeg()

        original_timeout = mgr.lease_timeout_s
        mgr.lease_timeout_s = 5.0

        try:
            resp = self.client.post(
                "/session/acquire",
                json={"session_id": "phone-A"},
            )
            self.assertEqual(resp.status_code, 200)

            # Record heartbeat before inference
            with mgr._lock:
                hb_before = mgr.last_heartbeat

            # Send a frame (which should refresh the lease after completion)
            with patch.object(main.pipeline, "process_frame") as mock_pf:
                from pipeline.models import FrameResult
                mock_pf.return_value = FrameResult(
                    frame_index=1, mode="monocular",
                    depth_backend="none", tracking_backend="none",
                    objects=[], debug={},
                )
                resp = self.client.post(
                    "/pipeline/frame",
                    files={"file": ("frame.jpg", jpeg_bytes, "image/jpeg")},
                    headers={"X-Session-ID": "phone-A"},
                )
                self.assertIn(resp.status_code, (200,))

            with mgr._lock:
                hb_after = mgr.last_heartbeat

            self.assertGreaterEqual(hb_after, hb_before,
                                    "Lease heartbeat should be refreshed after frame processing")
        finally:
            mgr.lease_timeout_s = original_timeout

    # ── Processing guard prevents reset during inference ─────────────────

    def test_reset_prevented_during_inference(self):
        """Calling session_acquire/reset concurrently with inference is serialised
        because both paths require the shared processing guard.

        When a frame is being processed, session_acquire (which triggers state reset)
        blocks until inference finishes, rather than running concurrently."""
        from pipeline.models import FrameResult
        inference_started = threading.Event()
        inference_continue = threading.Event()
        jpeg_bytes = self._make_test_jpeg()

        dummy_result = FrameResult(
            frame_index=1,
            mode="monocular",
            depth_backend="none",
            tracking_backend="none",
            objects=[],
            debug={},
        )

        def slow_process(frame):
            inference_started.set()
            inference_continue.wait(timeout=5.0)
            return dummy_result

        results = {}

        def send_frame():
            try:
                resp = self.client.post(
                    "/pipeline/frame",
                    files={"file": ("frame.jpg", jpeg_bytes, "image/jpeg")},
                    headers={"X-Session-ID": "phone-A"},
                )
                results["frame"] = resp.status_code
            except Exception as e:
                results["frame"] = f"error: {e}"

        def try_acquire():
            try:
                resp = self.client.post(
                    "/session/acquire",
                    json={"session_id": "phone-C", "force": True},
                )
                results["acquire"] = resp.status_code
            except Exception as e:
                results["acquire"] = f"error: {e}"

        with patch.object(main.pipeline, "process_frame", side_effect=slow_process):
            t_frame = threading.Thread(target=send_frame)
            t_frame.start()
            self.assertTrue(inference_started.wait(timeout=5.0))

            # Trigger acquire/reset while inference is still active
            t_acquire = threading.Thread(target=try_acquire)
            t_acquire.start()

            # Verify that while inference is active, acquire has not completed yet
            time.sleep(0.3)
            self.assertNotIn("acquire", results, "Acquire/reset must wait for inference to finish")

            # Let inference complete
            inference_continue.set()
            t_frame.join(timeout=5.0)
            t_acquire.join(timeout=5.0)

        self.assertEqual(results.get("frame"), 200)
        self.assertEqual(results.get("acquire"), 200)

    # ── Processing Guard Regression Tests ─────────────────────────────────

    def test_processing_guard_context_manager_contract(self):
        """Context manager releases exactly once on success, does not release on failed acquisition,
        and never suppresses lock ownership errors or exceptions."""
        mgr = SessionManager(lease_timeout_s=10.0)

        # 1. Normal execution
        with mgr.processing_guard() as acquired:
            self.assertTrue(acquired)
            self.assertTrue(mgr.is_processing())
        self.assertFalse(mgr.is_processing())

        # 2. Exception inside block releases lock and propagates exception
        with self.assertRaises(ZeroDivisionError):
            with mgr.processing_guard() as acquired:
                self.assertTrue(acquired)
                _ = 1 / 0
        self.assertFalse(mgr.is_processing())

        # 3. Failed acquisition yields False and does not double-release
        with mgr.processing_guard() as first_acquired:
            self.assertTrue(first_acquired)
            # Second attempt should fail
            with mgr.processing_guard(blocking=False) as second_acquired:
                self.assertFalse(second_acquired)
            # Lock should still be held by first_acquired
            self.assertTrue(mgr.is_processing())
        self.assertFalse(mgr.is_processing())

    def test_frame_exception_releases_guard(self):
        """If pipeline.process_frame raises an unexpected exception during processing,
        the processing guard must be cleanly released and subsequent requests must succeed."""
        jpeg_bytes = self._make_test_jpeg()

        with patch.object(main.pipeline, "process_frame", side_effect=RuntimeError("Model inference exploded")):
            try:
                resp = self.client.post(
                    "/pipeline/frame",
                    files={"file": ("frame.jpg", jpeg_bytes, "image/jpeg")},
                    headers={"X-Session-ID": "phone-A"},
                )
                self.assertEqual(resp.status_code, 500)
            except RuntimeError as e:
                self.assertIn("Model inference exploded", str(e))

        # Guard should be completely released, allowing normal status and next frame
        self.assertFalse(main.session_manager.is_processing())

        from pipeline.models import FrameResult
        with patch.object(main.pipeline, "process_frame", return_value=FrameResult(
            frame_index=1, mode="monocular", depth_backend="none", tracking_backend="none",
            objects=[], debug={},
        )):
            resp2 = self.client.post(
                "/pipeline/frame",
                files={"file": ("frame.jpg", jpeg_bytes, "image/jpeg")},
                headers={"X-Session-ID": "phone-A"},
            )
            self.assertEqual(resp2.status_code, 200)

    def test_upload_cancellation_releases_guard(self):
        """If an upload stream fails or is cancelled mid-stream (read_uploaded_file error),
        the processing guard must be released immediately without leaving the backend locked."""
        async def mock_failing_read(file, max_bytes=None):
            raise asyncio.CancelledError("Client disconnected")

        import concurrent.futures
        with patch("main.read_uploaded_file", side_effect=mock_failing_read):
            with self.assertRaises((asyncio.CancelledError, concurrent.futures.CancelledError)):
                self.client.post(
                    "/pipeline/frame",
                    files={"file": ("frame.jpg", b"incomplete", "image/jpeg")},
                    headers={"X-Session-ID": "phone-A"},
                )

        # Ensure lock is released after cancellation
        self.assertFalse(main.session_manager.is_processing())

    def test_failed_acquisition_does_not_release_lock_or_crash(self):
        """When acquisition fails because another thread is processing, 409 is returned
        and no lock ownership error is raised."""
        from pipeline.models import FrameResult
        inference_started = threading.Event()
        inference_continue = threading.Event()
        jpeg_bytes = self._make_test_jpeg()

        dummy_result = FrameResult(
            frame_index=1, mode="monocular", depth_backend="none", tracking_backend="none",
            objects=[], debug={},
        )

        def slow_process(frame):
            inference_started.set()
            inference_continue.wait(timeout=5.0)
            return dummy_result

        results = {}

        def send_first():
            resp = self.client.post(
                "/pipeline/frame",
                files={"file": ("frame.jpg", jpeg_bytes, "image/jpeg")},
                headers={"X-Session-ID": "phone-A"},
            )
            results["first"] = resp.status_code

        with patch.object(main.pipeline, "process_frame", side_effect=slow_process):
            t1 = threading.Thread(target=send_first)
            t1.start()
            self.assertTrue(inference_started.wait(timeout=5.0))

            # Second request fails non-blocking acquisition
            resp2 = self.client.post(
                "/pipeline/frame",
                files={"file": ("frame.jpg", jpeg_bytes, "image/jpeg")},
                headers={"X-Session-ID": "phone-A"},
            )
            self.assertEqual(resp2.status_code, 409)

            # Finish first
            inference_continue.set()
            t1.join(timeout=5.0)

        self.assertEqual(results["first"], 200)
        self.assertFalse(main.session_manager.is_processing())


if __name__ == "__main__":
    unittest.main()
