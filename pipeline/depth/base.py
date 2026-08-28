"""Depth backend interface."""

from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np

from pipeline.models import DepthMap


class BaseDepthBackend(ABC):
    name: str = "base"

    @abstractmethod
    def estimate(self, frame_bgr: np.ndarray) -> DepthMap:
        raise NotImplementedError

    @property
    @abstractmethod
    def provides_metric_depth(self) -> bool:
        raise NotImplementedError
