"""Deep SORT tracker placeholder for future swap-in."""

from __future__ import annotations

import numpy as np

from pipeline.models import TrackedObject
from pipeline.tracking.base import BaseTracker


class DeepSortTracker(BaseTracker):
    """
    TODO: Integrate Deep SORT (e.g. deep-sort-realtime or Ultralytics BoT-SORT variant).
    Keep the same BaseTracker interface so orchestrator code stays unchanged.
    """

    name = "deepsort"

    def __init__(self, model_path: str, conf: float = 0.25, target_classes: set[str] | None = None):
        self.model_path = model_path
        self.conf = conf
        self.target_classes = target_classes or set()

    def track(self, frame: np.ndarray) -> list[TrackedObject]:
        raise NotImplementedError(
            "Deep SORT backend not implemented yet. "
            "Set TRACKER_BACKEND='bytetrack' in pipeline/config.py, "
            "or implement DeepSortTracker here."
        )
