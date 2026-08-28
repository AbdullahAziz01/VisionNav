"""Tracker interface."""

from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np

from pipeline.models import TrackedObject


class BaseTracker(ABC):
    name: str = "base"

    @abstractmethod
    def track(self, frame: np.ndarray) -> list[TrackedObject]:
        raise NotImplementedError

    def reset(self) -> None:
        """Reset persistent track state between sessions."""
