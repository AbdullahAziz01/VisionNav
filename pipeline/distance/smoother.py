"""Temporal smoothing for per-track distances."""

from __future__ import annotations


class DistanceSmoother:
    def __init__(self, alpha: float = 0.35):
        self.alpha = alpha
        self._state: dict[int, float] = {}

    def update(self, track_id: int, distance_m: float) -> float:
        if track_id not in self._state:
            self._state[track_id] = distance_m
        else:
            self._state[track_id] = self.alpha * distance_m + (1.0 - self.alpha) * self._state[track_id]
        return self._state[track_id]

    def reset(self) -> None:
        self._state.clear()
