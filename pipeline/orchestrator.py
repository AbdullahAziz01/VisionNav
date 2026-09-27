"""VisionNav main orchestrator — with staggered-depth support."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from pipeline.camera import capture_frame, open_camera
from pipeline.config import PipelineConfig
from pipeline.depth import create_mono_depth_backend
from pipeline.distance import DistanceCalculator
from pipeline.distance.calculator import _sample_bbox_depth, _to_estimated_meters
from pipeline.bus_route.identifier import BusRouteIdentifier
from pipeline.models import DepthMap, FrameResult, ObjectDistance
from pipeline.stereo import create_stereo_depth_backend, detect_stereo_pair
from pipeline.tracking import create_tracker


class VisionNavPipeline:
    def __init__(self, config: PipelineConfig | None = None):
        self.config = config or PipelineConfig()
        self.tracker = create_tracker(
            self.config.tracker_backend,
            self.config.yolo_model,
            self.config.detection_conf,
            self.config.target_classes,
        )
        self.mono_depth = create_mono_depth_backend(
            self.config.mono_depth_backend,
            self.config.depth_anything_model,
            self.config.metric3d_checkpoint,
            midas_onnx_model_path=self.config.midas_onnx_model_path,
            midas_onnx_scale=self.config.midas_onnx_scale,
            midas_onnx_shift=self.config.midas_onnx_shift,
            midas_onnx_intra_op_threads=self.config.midas_onnx_intra_op_threads,
            midas_onnx_inter_op_threads=self.config.midas_onnx_inter_op_threads,
            depth_anything_input_size=self.config.depth_anything_input_size,
            depth_anything_threads=self.config.depth_anything_threads,
        )
        self.stereo_depth = create_stereo_depth_backend(self.config.stereo_depth_backend)
        self.distance_calc = DistanceCalculator(
            smoothing_alpha=self.config.temporal_smoothing_alpha,
            relative_scale_m=self.config.relative_depth_scale_m,
            use_geometric=self.config.use_geometric_distance,
            geometric_focal_ratio=self.config.geometric_focal_ratio,
            object_real_heights_m=self.config.object_real_heights_m,
        )
        self.stereo_status = detect_stereo_pair(self.config.stereo_calibration_path)
        self.frame_index = 0
        self._stereo_caps: tuple[cv2.VideoCapture, cv2.VideoCapture] | None = None

        # Staggered-depth state
        self._latest_mono_depth: DepthMap | None = None
        self._prev_track_ids: set[int] = set()
        self.bus_routes = BusRouteIdentifier()

    @property
    def active_mode(self) -> str:
        return "stereo" if self.stereo_status.available else "monocular"

    def _read_stereo_frames(self) -> tuple[np.ndarray, np.ndarray] | None:
        cal = self.stereo_status.calibration
        if cal is None:
            return None

        if self._stereo_caps is None:
            left = open_camera(cal.left_camera_index)
            right = open_camera(cal.right_camera_index)
            if not left.isOpened() or not right.isOpened():
                return None
            self._stereo_caps = (left, right)

        left_cap, right_cap = self._stereo_caps
        ok_l, left = left_cap.read()
        ok_r, right = right_cap.read()
        if not ok_l or not ok_r or left is None or right is None:
            return None
        return left, right

    def process_frame(
        self,
        frame_bgr: np.ndarray,
        stereo_pair: tuple[np.ndarray, np.ndarray] | None = None,
    ) -> FrameResult:
        self.frame_index += 1
        tracked = self.tracker.track(frame_bgr)

        # ── Stereo path (unchanged) ──────────────────────────────────────────
        if self.stereo_status.available and stereo_pair is not None:
            left, right = stereo_pair
            depth = self.stereo_depth.estimate(left, right, self.stereo_status.calibration)
            mode = "stereo"
            depth_backend = self.stereo_depth.name
            objects = self.distance_calc.compute(
                tracked, depth,
                depth_backend=depth_backend,
                tracking_backend=self.tracker.name,
            )
            self._prev_track_ids = {obj.track_id for obj in tracked}
            result = FrameResult(
                frame_index=self.frame_index,
                mode=mode,
                depth_backend=depth_backend,
                tracking_backend=self.tracker.name,
                objects=objects,
                debug={
                    "depth_scale_note": depth.scale_note,
                    "stereo_status": self.stereo_status.reason,
                    "num_tracks": len(objects),
                    "depth_computed_this_frame": True,
                },
            )
            self._attach_bus_routes(frame_bgr, result.objects)
            return result

        # ── Monocular path (staggered or synchronous) ────────────────────────
        interval = self.config.depth_computation_interval
        depth_is_new = (interval <= 1) or (self.frame_index % interval == 0)

        if depth_is_new:
            depth = self.mono_depth.estimate(frame_bgr)
            self._latest_mono_depth = depth
        else:
            depth = self._latest_mono_depth

        mode = "monocular"
        depth_backend = self.mono_depth.name

        if depth is None:
            # No depth map yet (first frames with interval > 1)
            objects = [
                ObjectDistance(
                    track_id=obj.track_id,
                    class_name=obj.class_name,
                    confidence=obj.confidence,
                    bbox_xyxy=obj.bbox_xyxy,
                    estimated_distance_m=None,
                    raw_depth_value=0.0,
                    is_metric=False,
                    distance_label="distance unavailable (no depth map yet)",
                    depth_backend=depth_backend,
                    tracking_backend=self.tracker.name,
                )
                for obj in tracked
            ]
        elif depth_is_new or interval <= 1:
            # Full compute with the fresh depth map — use normal pipeline path
            objects = self.distance_calc.compute(
                tracked, depth,
                depth_backend=depth_backend,
                tracking_backend=self.tracker.name,
            )
        else:
            # Staggered: reuse previous depth map.
            # Guard against attaching stale depth to brand-new track IDs.
            objects = []
            for obj in tracked:
                if obj.track_id not in self._prev_track_ids:
                    # New track — no reliable depth association until next depth frame
                    objects.append(ObjectDistance(
                        track_id=obj.track_id,
                        class_name=obj.class_name,
                        confidence=obj.confidence,
                        bbox_xyxy=obj.bbox_xyxy,
                        estimated_distance_m=None,
                        raw_depth_value=0.0,
                        is_metric=False,
                        distance_label="distance unavailable (new track, awaiting fresh depth)",
                        depth_backend=depth_backend,
                        tracking_backend=self.tracker.name,
                    ))
                    continue

                raw = _sample_bbox_depth(depth.values, obj.bbox_xyxy)
                if raw is None:
                    objects.append(ObjectDistance(
                        track_id=obj.track_id,
                        class_name=obj.class_name,
                        confidence=obj.confidence,
                        bbox_xyxy=obj.bbox_xyxy,
                        estimated_distance_m=None,
                        raw_depth_value=0.0,
                        is_metric=depth.is_metric,
                        distance_label="distance unavailable",
                        depth_backend=depth_backend,
                        tracking_backend=self.tracker.name,
                    ))
                    continue

                from pipeline.config import MIN_VALID_DEPTH_M, MAX_VALID_DEPTH_M
                meters, is_metric, label = _to_estimated_meters(
                    raw, depth, self.distance_calc.relative_scale_m
                )
                if meters is not None:
                    if meters < MIN_VALID_DEPTH_M or meters > MAX_VALID_DEPTH_M:
                        label = f"{meters:.1f} m (estimated, out of expected range)"
                    else:
                        meters = self.distance_calc.smoother.update(obj.track_id, meters)
                        label = (
                            f"{meters:.1f} m (estimated metric)"
                            if is_metric
                            else f"{meters:.1f} m (estimated, relative-scaled — validate experimentally)"
                        )
                objects.append(ObjectDistance(
                    track_id=obj.track_id,
                    class_name=obj.class_name,
                    confidence=obj.confidence,
                    bbox_xyxy=obj.bbox_xyxy,
                    estimated_distance_m=meters,
                    raw_depth_value=raw,
                    is_metric=is_metric,
                    distance_label=label,
                    depth_backend=depth_backend,
                    tracking_backend=self.tracker.name,
                ))

        self._prev_track_ids = {obj.track_id for obj in tracked}

        result = FrameResult(
            frame_index=self.frame_index,
            mode=mode,
            depth_backend=depth_backend,
            tracking_backend=self.tracker.name,
            objects=objects,
            debug={
                "depth_scale_note": depth.scale_note if depth else "",
                "stereo_status": self.stereo_status.reason,
                "num_tracks": len(objects),
                "depth_computed_this_frame": depth_is_new,
            },
        )
        self._attach_bus_routes(frame_bgr, result.objects)
        return result

    def _attach_bus_routes(self, frame_bgr: np.ndarray, objects: list[ObjectDistance]) -> None:
        """Add a stable bus-route result after tracking and distance are finished."""
        try:
            self.bus_routes.apply(frame_bgr, objects, self.frame_index)
        except Exception:
            return

    def process_camera_snapshot(self) -> tuple[FrameResult | None, np.ndarray | None, dict]:
        ok, frame, cam_debug = capture_frame(
            self.config.camera_index,
            warmup_frames=self.config.camera_warmup_frames,
        )
        if not ok or frame is None:
            return None, None, cam_debug

        stereo_pair = self._read_stereo_frames() if self.stereo_status.available else None
        result = self.process_frame(frame, stereo_pair=stereo_pair)
        result.debug.update(cam_debug)
        return result, frame, cam_debug

    def release(self) -> None:
        if self._stereo_caps is not None:
            self._stereo_caps[0].release()
            self._stereo_caps[1].release()
            self._stereo_caps = None

    @staticmethod
    def save_debug_snapshot(frame: np.ndarray, path: Path) -> str:
        path.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(path), frame)
        return str(path)
