"""
MiDaS legacy backend — DISABLED.

Kept for reference only. The active VisionNav pipeline no longer uses MiDaS.
Use depth_anything_v2 or metric3d instead.
See depth_test.py for the old standalone MiDaS script.
"""

from __future__ import annotations

import numpy as np

from pipeline.depth.base import BaseDepthBackend
from pipeline.models import DepthMap


class MiDaSLegacyBackend(BaseDepthBackend):
    name = "midas_legacy_disabled"
    ACTIVE = False

    def __init__(self):
        raise RuntimeError(
            "MiDaS is disabled in the active pipeline. "
            "Use Depth Anything V2 or Metric3D via pipeline/config.py."
        )

    @property
    def provides_metric_depth(self) -> bool:
        return False

    def estimate(self, frame_bgr: np.ndarray) -> DepthMap:
        raise RuntimeError("MiDaS legacy backend is disabled.")
