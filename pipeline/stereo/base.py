"""Stereo depth backend interface."""

from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np

from pipeline.models import DepthMap
from pipeline.stereo.detector import StereoCalibration


class BaseStereoDepthBackend(ABC):
    name: str = "base"

    @abstractmethod
    def estimate(self, left_bgr: np.ndarray, right_bgr: np.ndarray, calibration: StereoCalibration) -> DepthMap:
        raise NotImplementedError
