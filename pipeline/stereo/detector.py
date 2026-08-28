"""Detect whether a usable calibrated stereo camera pair is available."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np


@dataclass
class StereoCalibration:
    left_camera_index: int
    right_camera_index: int
    baseline_m: float
    focal_length_px: float
    image_width: int
    image_height: int
    # TODO: full rectification maps from Android / OpenCV stereoCalibrate
    q_matrix: list[list[float]] | None = None


@dataclass
class StereoPairStatus:
    available: bool
    reason: str
    calibration: StereoCalibration | None = None


def _frames_overlap(left: np.ndarray, right: np.ndarray) -> bool:
    """Reject duplicated feeds or completely unrelated cameras."""
    if left.shape != right.shape:
        return False

    diff = np.mean(cv2.absdiff(left, right))
    if diff < 2.0:
        return False  # likely same camera duplicated

    # Require some structural similarity without being identical.
    left_gray = cv2.cvtColor(left, cv2.COLOR_BGR2GRAY)
    right_gray = cv2.cvtColor(right, cv2.COLOR_BGR2GRAY)
    score = cv2.matchTemplate(left_gray, right_gray, cv2.TM_CCOEFF_NORMED).max()
    return score > 0.35


def load_calibration(path: Path) -> StereoCalibration | None:
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    required = ["left_camera_index", "right_camera_index", "baseline_m", "focal_length_px"]
    if not all(k in data for k in required):
        return None
    return StereoCalibration(
        left_camera_index=int(data["left_camera_index"]),
        right_camera_index=int(data["right_camera_index"]),
        baseline_m=float(data["baseline_m"]),
        focal_length_px=float(data["focal_length_px"]),
        image_width=int(data.get("image_width", 640)),
        image_height=int(data.get("image_height", 480)),
        q_matrix=data.get("q_matrix"),
    )


def detect_stereo_pair(calibration_path: Path) -> StereoPairStatus:
    """
    A stereo pair is considered valid only when:
      1) calibration file exists with baseline + intrinsics
      2) both camera indices open successfully
      3) frames overlap but are not identical

    TODO (Android):
      - Enumerate CameraCharacteristics for physical multi-camera setups.
      - Confirm synchronized left/right streams and rectification support.
      - Load device-specific intrinsics/extrinsics from factory or on-device calibration.
    """
    calibration = load_calibration(calibration_path)
    if calibration is None:
        return StereoPairStatus(
            available=False,
            reason=f"No valid calibration at {calibration_path}",
        )

    left_cap = cv2.VideoCapture(calibration.left_camera_index, cv2.CAP_DSHOW)
    right_cap = cv2.VideoCapture(calibration.right_camera_index, cv2.CAP_DSHOW)
    if not left_cap.isOpened() or not right_cap.isOpened():
        left_cap.release()
        right_cap.release()
        return StereoPairStatus(
            available=False,
            reason="Could not open configured left/right camera indices",
            calibration=calibration,
        )

    ok_l, left = left_cap.read()
    ok_r, right = right_cap.read()
    left_cap.release()
    right_cap.release()

    if not ok_l or not ok_r or left is None or right is None:
        return StereoPairStatus(
            available=False,
            reason="Failed to read frames from one or both cameras",
            calibration=calibration,
        )

    if not _frames_overlap(left, right):
        return StereoPairStatus(
            available=False,
            reason="Camera feeds do not appear to be a valid overlapping stereo pair",
            calibration=calibration,
        )

    return StereoPairStatus(
        available=True,
        reason="Valid calibrated stereo pair detected",
        calibration=calibration,
    )
