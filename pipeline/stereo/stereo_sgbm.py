"""OpenCV StereoSGBM depth backend."""

from __future__ import annotations

import cv2
import numpy as np

from pipeline.models import DepthMap
from pipeline.stereo.base import BaseStereoDepthBackend
from pipeline.stereo.detector import StereoCalibration


class StereoSGBMBackend(BaseStereoDepthBackend):
    name = "stereo_sgbm"

    def estimate(self, left_bgr: np.ndarray, right_bgr: np.ndarray, calibration: StereoCalibration) -> DepthMap:
        left_gray = cv2.cvtColor(left_bgr, cv2.COLOR_BGR2GRAY)
        right_gray = cv2.cvtColor(right_bgr, cv2.COLOR_BGR2GRAY)

        stereo = cv2.StereoSGBM_create(
            minDisparity=0,
            numDisparities=128,
            blockSize=5,
            P1=8 * 3 * 5 ** 2,
            P2=32 * 3 * 5 ** 2,
            disp12MaxDiff=1,
            uniquenessRatio=10,
            speckleWindowSize=100,
            speckleRange=32,
        )
        disparity = stereo.compute(left_gray, right_gray).astype(np.float32) / 16.0
        disparity[disparity <= 0] = np.nan

        depth_m = (calibration.baseline_m * calibration.focal_length_px) / disparity
        depth_m = np.nan_to_num(depth_m, nan=0.0, posinf=0.0, neginf=0.0)

        return DepthMap(
            values=depth_m.astype(np.float32),
            is_metric=True,
            unit="m",
            backend_name=self.name,
            scale_note=(
                "StereoSGBM metric depth from baseline * focal / disparity. "
                "Accuracy depends on calibration quality; validate experimentally."
            ),
        )
