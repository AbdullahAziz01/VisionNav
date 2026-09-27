"""Geometric (pinhole) metric distance from bounding-box height.

For KNOWN-SIZE object classes (person, car, bus, ...), the bounding-box height
in the image is a stable, calibratable cue for metric distance — far more
reliable than MiDaS relative depth, which is scene-normalized per frame.

Pinhole model (resolution-independent form):
    Z = H_real * K / (bbox_height_px / image_height_px)
where
    H_real = assumed real-world object height in metres
    K      = focal_length_px / image_height_px  (GEOMETRIC_FOCAL_RATIO)

K is CAMERA SPECIFIC (depends on vertical field of view). Calibrate it on the
same camera that produces the frames — a laptop webcam value is wrong for a
phone rear camera.

Truncation: if the object touches the top/bottom image edge, its true height is
not visible, so bbox height under-represents it and the distance is
over-estimated. Those samples are flagged rather than silently trusted.
"""

from __future__ import annotations

from dataclasses import dataclass

EDGE_TOLERANCE_PX = 3.0


@dataclass
class GeometricEstimate:
    distance_m: float | None
    height_fraction: float
    truncated_top: bool
    truncated_bottom: bool

    @property
    def truncated(self) -> bool:
        return self.truncated_top or self.truncated_bottom

    @property
    def fully_visible(self) -> bool:
        return not self.truncated


class GeometricDistanceEstimator:
    def __init__(self, focal_ratio: float, real_heights_m: dict[str, float]):
        self.focal_ratio = focal_ratio
        self.real_heights_m = real_heights_m

    def supports(self, class_name: str) -> bool:
        return class_name in self.real_heights_m

    def estimate_detailed(
        self,
        class_name: str,
        bbox_xyxy: tuple[float, float, float, float],
        image_height_px: int,
    ) -> GeometricEstimate | None:
        real_height = self.real_heights_m.get(class_name)
        if real_height is None or image_height_px <= 0 or self.focal_ratio <= 0:
            return None

        _, y1, _, y2 = bbox_xyxy
        y1, y2 = float(y1), float(y2)
        bbox_height_px = y2 - y1
        if bbox_height_px <= 1.0:
            return None

        height_fraction = bbox_height_px / float(image_height_px)
        distance_m = real_height * self.focal_ratio / height_fraction

        return GeometricEstimate(
            distance_m=distance_m,
            height_fraction=height_fraction,
            truncated_top=y1 <= EDGE_TOLERANCE_PX,
            truncated_bottom=y2 >= image_height_px - EDGE_TOLERANCE_PX,
        )

    def estimate(
        self,
        class_name: str,
        bbox_xyxy: tuple[float, float, float, float],
        image_height_px: int,
    ) -> float | None:
        detail = self.estimate_detailed(class_name, bbox_xyxy, image_height_px)
        return detail.distance_m if detail else None
