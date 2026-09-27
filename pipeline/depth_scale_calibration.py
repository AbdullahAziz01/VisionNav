"""Per-camera linear correction for metric depth-model output.

Depth Anything V2 Metric learned its "metres" from the training cameras
(Hypersim indoor / Virtual KITTI outdoor). A phone lens has a different focal
length, so the model's output is consistently mis-scaled for that phone.
Systematic error like this is corrected well by a linear fit:

    Z_corrected = scale * Z_predicted + shift

fitted from a few ground-truth points (stand at 1, 2, 3, 4, 5 m, tape-measured).
The fit is stored in JSON and applied live to every distance.

This does NOT make monocular depth exact. Expect residual error around
5-10 % after calibration; it removes the large constant bias, not noise.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

CALIBRATION_PATH = Path("config/depth_scale_calibration.json")


def load_depth_scale(path: Path = CALIBRATION_PATH) -> tuple[float, float] | None:
    """Return (scale, shift) previously saved, or None."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        scale = float(data["scale"])
        shift = float(data.get("shift", 0.0))
        return (scale, shift) if scale > 0 else None
    except Exception:
        return None


def save_depth_scale(scale: float, shift: float, meta: dict, path: Path = CALIBRATION_PATH) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"scale": round(float(scale), 6), "shift": round(float(shift), 6), **meta}
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return str(path)


@dataclass
class DepthScaleSession:
    """Collects raw (uncorrected) predicted distances at one known distance."""

    distance_m: float
    target_class: str = "person"
    predictions: list[float] = field(default_factory=list)

    def add_sample(self, predicted_m: float) -> None:
        if np.isfinite(predicted_m) and predicted_m > 0:
            self.predictions.append(float(predicted_m))

    @property
    def count(self) -> int:
        return len(self.predictions)


class DepthScaleCollector:
    """Server-side state machine driven by the /calibrate/depth/* endpoints."""

    MIN_SAMPLES = 5

    def __init__(self) -> None:
        self.active: DepthScaleSession | None = None
        self.points: list[dict] = []

    def start(self, distance_m: float, target_class: str) -> None:
        self.active = DepthScaleSession(distance_m=distance_m, target_class=target_class)

    def feed(self, class_name: str, predicted_m: float) -> None:
        session = self.active
        if session is None or class_name != session.target_class:
            return
        session.add_sample(predicted_m)

    def stop(self) -> dict:
        session = self.active
        self.active = None
        if session is None:
            return {"error": "No depth calibration session was running."}
        if session.count < self.MIN_SAMPLES:
            return {
                "error": f"Only {session.count} samples captured (need >= {self.MIN_SAMPLES}).",
                "hint": (
                    f"Keep the {session.target_class} in view while the app streams for a "
                    "few seconds, then open /calibrate/depth/stop"
                ),
            }
        preds = np.array(session.predictions, dtype=np.float64)
        point = {
            "distance_m": session.distance_m,
            "predicted_median_m": round(float(np.median(preds)), 4),
            "predicted_std_m": round(float(preds.std()), 4),
            "samples": session.count,
        }
        self.points.append(point)
        return point

    def fit(self) -> dict:
        """Least-squares  true = scale * predicted + shift  over collected points."""
        if not self.points:
            return {"error": "No points yet. Use /calibrate/depth/start then /calibrate/depth/stop."}

        pred = np.array([p["predicted_median_m"] for p in self.points], dtype=np.float64)
        true = np.array([p["distance_m"] for p in self.points], dtype=np.float64)

        if pred.size == 1 or np.ptp(pred) < 1e-6:
            # One point (or identical predictions): scale only, no shift.
            scale = float(np.sum(true * pred) / np.sum(pred * pred))
            shift = 0.0
            mode = "scale_only"
        else:
            scale, shift = np.polyfit(pred, true, deg=1)
            scale, shift = float(scale), float(shift)
            mode = "scale_and_shift"

        if scale <= 0:
            return {"error": f"Fit produced a non-positive scale ({scale:.4f}); recollect points."}

        before = pred - true
        after = (scale * pred + shift) - true
        return {
            "scale": scale,
            "shift": shift,
            "mode": mode,
            "num_points": int(pred.size),
            "mae_before_m": float(np.mean(np.abs(before))),
            "mae_after_m": float(np.mean(np.abs(after))),
            "rmse_before_m": float(np.sqrt(np.mean(before**2))),
            "rmse_after_m": float(np.sqrt(np.mean(after**2))),
            "points": [
                {
                    **p,
                    "corrected_m": round(float(scale * p["predicted_median_m"] + shift), 3),
                    "error_before_m": round(float(p["predicted_median_m"] - p["distance_m"]), 3),
                    "error_after_m": round(
                        float(scale * p["predicted_median_m"] + shift - p["distance_m"]), 3
                    ),
                }
                for p in self.points
            ],
        }

    def reset(self) -> None:
        self.active = None
        self.points = []
