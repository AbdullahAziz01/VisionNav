"""Convert depth maps + tracked boxes into estimated metric distances."""

from __future__ import annotations

import numpy as np

from pipeline.config import MIN_VALID_DEPTH_M, MAX_VALID_DEPTH_M, RELATIVE_DEPTH_SCALE_M
from pipeline.distance.smoother import DistanceSmoother
from pipeline.models import DepthMap, ObjectDistance, TrackedObject


def _sample_bbox_depth(depth_map: np.ndarray, bbox_xyxy: tuple[float, float, float, float]) -> float | None:
    h, w = depth_map.shape[:2]
    x1, y1, x2, y2 = bbox_xyxy
    x1, y1 = max(0, int(x1)), max(0, int(y1))
    x2, y2 = min(w, int(x2)), min(h, int(y2))
    if x2 <= x1 or y2 <= y1:
        return None

    # Central 50% region reduces background bleed at bbox edges.
    bw, bh = x2 - x1, y2 - y1
    cx1 = x1 + int(bw * 0.25)
    cx2 = x2 - int(bw * 0.25)
    cy1 = y1 + int(bh * 0.25)
    cy2 = y2 - int(bh * 0.25)
    roi = depth_map[cy1:cy2, cx1:cx2]
    if roi.size == 0:
        roi = depth_map[y1:y2, x1:x2]
    valid = roi[np.isfinite(roi) & (roi > 0)]
    if valid.size == 0:
        return None
    return float(np.median(valid))


def _to_estimated_meters(raw_value: float, depth: DepthMap, relative_scale_m: float) -> tuple[float | None, bool, str]:
    if depth.is_metric and depth.unit == "m":
        meters = raw_value
        label = f"{meters:.1f} m (estimated metric)"
        return meters, True, label

    # Relative depth: higher value meaning closer/farther depends on model.
    # Depth Anything relative output is inverse-depth-like; normalize then scale.
    normalized = float(raw_value)
    meters = relative_scale_m / max(normalized, 1e-3)
    label = f"{meters:.1f} m (estimated, relative-scaled — validate experimentally)"
    return meters, False, label


class DistanceCalculator:
    def __init__(self, smoothing_alpha: float, relative_scale_m: float = RELATIVE_DEPTH_SCALE_M):
        self.relative_scale_m = relative_scale_m
        self.smoother = DistanceSmoother(alpha=smoothing_alpha)

    def compute(
        self,
        tracked_objects: list[TrackedObject],
        depth: DepthMap,
        depth_backend: str,
        tracking_backend: str,
    ) -> list[ObjectDistance]:
        results: list[ObjectDistance] = []
        for obj in tracked_objects:
            raw = _sample_bbox_depth(depth.values, obj.bbox_xyxy)
            if raw is None:
                results.append(
                    ObjectDistance(
                        track_id=obj.track_id,
                        class_name=obj.class_name,
                        confidence=obj.confidence,
                        bbox_xyxy=obj.bbox_xyxy,
                        estimated_distance_m=None,
                        raw_depth_value=0.0,
                        is_metric=depth.is_metric,
                        distance_label="distance unavailable",
                        depth_backend=depth_backend,
                        tracking_backend=tracking_backend,
                    )
                )
                continue

            meters, is_metric, label = _to_estimated_meters(raw, depth, self.relative_scale_m)
            if meters is not None:
                if meters < MIN_VALID_DEPTH_M or meters > MAX_VALID_DEPTH_M:
                    label = f"{meters:.1f} m (estimated, out of expected range)"
                else:
                    meters = self.smoother.update(obj.track_id, meters)
                    label = f"{meters:.1f} m (estimated metric)" if is_metric else (
                        f"{meters:.1f} m (estimated, relative-scaled — validate experimentally)"
                    )

            results.append(
                ObjectDistance(
                    track_id=obj.track_id,
                    class_name=obj.class_name,
                    confidence=obj.confidence,
                    bbox_xyxy=obj.bbox_xyxy,
                    estimated_distance_m=meters,
                    raw_depth_value=raw,
                    is_metric=is_metric,
                    distance_label=label,
                    depth_backend=depth_backend,
                    tracking_backend=tracking_backend,
                )
            )
        return results

    def reset(self) -> None:
        self.smoother.reset()
