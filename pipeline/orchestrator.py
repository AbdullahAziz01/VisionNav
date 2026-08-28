"""VisionNav main orchestrator."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from pipeline.camera import capture_frame, open_camera
from pipeline.config import PipelineConfig
from pipeline.depth import create_mono_depth_backend
from pipeline.distance import DistanceCalculator
from pipeline.models import FrameResult
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
        )
        self.stereo_depth = create_stereo_depth_backend(self.config.stereo_depth_backend)
        self.distance_calc = DistanceCalculator(
            smoothing_alpha=self.config.temporal_smoothing_alpha,
            relative_scale_m=self.config.relative_depth_scale_m,
        )
        self.stereo_status = detect_stereo_pair(self.config.stereo_calibration_path)
        self.frame_index = 0
        self._stereo_caps: tuple[cv2.VideoCapture, cv2.VideoCapture] | None = None

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

    def process_frame(self, frame_bgr: np.ndarray, stereo_pair: tuple[np.ndarray, np.ndarray] | None = None) -> FrameResult:
        self.frame_index += 1
        tracked = self.tracker.track(frame_bgr)

        if self.stereo_status.available and stereo_pair is not None:
            left, right = stereo_pair
            depth = self.stereo_depth.estimate(left, right, self.stereo_status.calibration)
            mode = "stereo"
            depth_backend = self.stereo_depth.name
        else:
            depth = self.mono_depth.estimate(frame_bgr)
            mode = "monocular"
            depth_backend = self.mono_depth.name

        objects = self.distance_calc.compute(
            tracked,
            depth,
            depth_backend=depth_backend,
            tracking_backend=self.tracker.name,
        )

        return FrameResult(
            frame_index=self.frame_index,
            mode=mode,
            depth_backend=depth_backend,
            tracking_backend=self.tracker.name,
            objects=objects,
            debug={
                "depth_scale_note": depth.scale_note,
                "stereo_status": self.stereo_status.reason,
                "num_tracks": len(objects),
            },
        )

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
