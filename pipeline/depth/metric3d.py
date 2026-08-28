"""Metric3D backend (optional checkpoint-based loading)."""

from __future__ import annotations

import cv2
import numpy as np

from pipeline.depth.base import BaseDepthBackend
from pipeline.models import DepthMap


class Metric3DBackend(BaseDepthBackend):
    """
    Metric3D integration hook.

    TODO (Android / deployment):
      - Convert Metric3D weights to mobile-friendly format (ONNX/TFLite).
      - Provide intrinsics from Android CameraCharacteristics.
      - Validate estimated metric depth with MAE/RMSE on a local test set.
    """

    name = "metric3d"

    def __init__(self, checkpoint_path: str = ""):
        self.checkpoint_path = checkpoint_path
        self._model = None

    @property
    def provides_metric_depth(self) -> bool:
        return True

    def _load(self):
        if self._model is not None:
            return
        if not self.checkpoint_path:
            raise RuntimeError(
                "Metric3D checkpoint not configured. "
                "Set METRIC3D_CHECKPOINT in pipeline/config.py "
                "or use depth_anything_v2 metric variant."
            )
        # TODO: load official Metric3D inference code + checkpoint here.
        raise NotImplementedError(
            "Metric3D loader not wired yet. Place checkpoint and implement model forward pass."
        )

    def estimate(self, frame_bgr: np.ndarray) -> DepthMap:
        self._load()
        depth = self._model(frame_bgr)
        return DepthMap(
            values=depth.astype(np.float32),
            is_metric=True,
            unit="m",
            backend_name=self.name,
            scale_note=(
                "Metric3D estimated metric depth (m). "
                "Requires experimental validation against ground-truth distances."
            ),
        )

    @staticmethod
    def placeholder_from_relative(relative_depth: np.ndarray, focal_length_px: float, scale_hint: float) -> DepthMap:
        """
        Development fallback when Metric3D weights are unavailable.
        Uses a simple inverse-depth heuristic — NOT validated metric output.
        """
        rel = relative_depth.astype(np.float32)
        rel = (rel - rel.min()) / max(rel.max() - rel.min(), 1e-6)
        pseudo_metric = scale_hint / np.clip(rel + 0.05, 0.05, None)
        return DepthMap(
            values=pseudo_metric,
            is_metric=False,
            unit="relative_scaled",
            backend_name="metric3d_placeholder",
            scale_note=(
                "Placeholder pseudo-metric map from relative depth. "
                "Replace with real Metric3D inference and calibration."
            ),
        )
