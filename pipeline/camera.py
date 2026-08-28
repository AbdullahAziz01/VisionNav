"""Camera helpers."""

from __future__ import annotations

import cv2
import numpy as np


def open_camera(index: int = 0) -> cv2.VideoCapture:
    cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)
    if not cap.isOpened():
        cap = cv2.VideoCapture(index)
    return cap


def capture_frame(index: int = 0, warmup_frames: int = 15) -> tuple[bool, np.ndarray | None, dict]:
    cap = open_camera(index)
    if not cap.isOpened():
        return False, None, {"error": "camera_not_opened", "camera_index": index}

    frame = None
    for _ in range(max(warmup_frames, 1)):
        ret, frame = cap.read()
        if not ret:
            break
    cap.release()

    if frame is None:
        return False, None, {"error": "no_frame", "camera_index": index}

    debug = {
        "camera_index": index,
        "shape": [int(frame.shape[0]), int(frame.shape[1]), int(frame.shape[2])],
        "mean_pixel": float(np.mean(frame)),
    }
    return True, frame, debug
