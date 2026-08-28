"""Shared data models for the VisionNav pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class TrackedObject:
    track_id: int
    class_name: str
    confidence: float
    bbox_xyxy: tuple[float, float, float, float]


@dataclass
class DepthMap:
    """Depth map returned by a depth backend."""

    values: np.ndarray
    is_metric: bool
    unit: str
    backend_name: str
    scale_note: str


@dataclass
class ObjectDistance:
    track_id: int
    class_name: str
    confidence: float
    bbox_xyxy: tuple[float, float, float, float]
    estimated_distance_m: float | None
    raw_depth_value: float
    is_metric: bool
    distance_label: str
    depth_backend: str
    tracking_backend: str


@dataclass
class FrameResult:
    frame_index: int
    mode: str  # "stereo" or "monocular"
    depth_backend: str
    tracking_backend: str
    objects: list[ObjectDistance] = field(default_factory=list)
    debug: dict = field(default_factory=dict)

    def format_lines(self) -> list[str]:
        header = f"Frame {self.frame_index}:"
        if not self.objects:
            return [header, "  (no tracked objects)"]
        lines = [header]
        for obj in self.objects:
            lines.append(f"  {obj.class_name.title()} ID {obj.track_id} → {obj.distance_label}")
        return lines
