"""RAFT-Stereo backend placeholder."""

from __future__ import annotations

import numpy as np

from pipeline.models import DepthMap
from pipeline.stereo.base import BaseStereoDepthBackend
from pipeline.stereo.detector import StereoCalibration


class RaftStereoBackend(BaseStereoDepthBackend):
    """
    TODO:
      - Integrate RAFT-Stereo inference (PyTorch -> ONNX for Android).
      - Feed rectified left/right frames from Android stereo camera API.
    """

    name = "raft_stereo"

    def estimate(self, left_bgr: np.ndarray, right_bgr: np.ndarray, calibration: StereoCalibration) -> DepthMap:
        raise NotImplementedError(
            "RAFT-Stereo backend not implemented yet. "
            "Set STEREO_DEPTH_BACKEND='stereo_sgbm' in pipeline/config.py."
        )
