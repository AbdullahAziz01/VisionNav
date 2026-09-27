"""Runtime geometric focal-ratio calibration (per camera).

GEOMETRIC_FOCAL_RATIO (K = focal_length_px / image_height_px) is CAMERA
SPECIFIC. A laptop webcam and a phone rear camera have different fields of
view, so a K calibrated on one is wrong on the other.

This module lets K be calibrated from the frames the phone actually sends,
stored in JSON, and applied live without editing code.

    K = Z_true * (bbox_height_px / image_height_px) / H_real
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

CALIBRATION_PATH = Path("config/geometric_calibration.json")


def load_focal_ratio(path: Path = CALIBRATION_PATH) -> float | None:
    """Return a previously calibrated focal ratio, or None."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        value = float(data["focal_ratio"])
        return value if value > 0 else None
    except Exception:
        return None


def save_focal_ratio(focal_ratio: float, meta: dict, path: Path = CALIBRATION_PATH) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"focal_ratio": round(float(focal_ratio), 6), **meta}
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return str(path)


@dataclass
class CalibrationSession:
    """Collects bbox height fractions at a known ground-truth distance."""

    distance_m: float
    object_height_m: float
    target_class: str = "person"
    fractions: list[float] = field(default_factory=list)
    rejected_truncated: int = 0

    def add_sample(self, height_fraction: float) -> None:
        if height_fraction > 0:
            self.fractions.append(float(height_fraction))

    @property
    def count(self) -> int:
        return len(self.fractions)

    def focal_ratio(self) -> float | None:
        if not self.fractions:
            return None
        median_fraction = float(np.median(self.fractions))
        return self.distance_m * median_fraction / self.object_height_m


class CalibrationCollector:
    """Server-side state machine driven by HTTP calibration endpoints."""

    def __init__(self) -> None:
        self.active: CalibrationSession | None = None
        self.points: list[dict] = []

    def start(self, distance_m: float, object_height_m: float, target_class: str) -> None:
        self.active = CalibrationSession(
            distance_m=distance_m,
            object_height_m=object_height_m,
            target_class=target_class,
        )

    def feed(self, class_name: str, height_fraction: float, truncated: bool) -> None:
        session = self.active
        if session is None or class_name != session.target_class:
            return
        if truncated:
            session.rejected_truncated += 1
            return
        session.add_sample(height_fraction)

    def stop(self) -> dict:
        session = self.active
        self.active = None
        if session is None:
            return {"error": "No calibration session was running."}

        k = session.focal_ratio()
        if k is None:
            return {
                "error": "No valid samples captured.",
                "rejected_truncated": session.rejected_truncated,
                "hint": "Keep the whole body inside the frame, then retry.",
            }

        point = {
            "distance_m": session.distance_m,
            "object_height_m": session.object_height_m,
            "median_height_fraction": round(float(np.median(session.fractions)), 5),
            "samples": session.count,
            "rejected_truncated": session.rejected_truncated,
            "focal_ratio": round(k, 5),
        }
        self.points.append(point)
        return point

    def fit(self) -> dict:
        if not self.points:
            return {"error": "No calibration points yet. Use /calibrate/start then /calibrate/stop."}
        ks = np.array([p["focal_ratio"] for p in self.points], dtype=np.float64)
        return {
            "focal_ratio": float(ks.mean()),
            "focal_ratio_std": float(ks.std()),
            "num_points": int(ks.size),
            "points": self.points,
        }

    def reset(self) -> None:
        self.active = None
        self.points = []
