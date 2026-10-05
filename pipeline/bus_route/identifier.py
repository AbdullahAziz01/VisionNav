"""Attach a stable Metrobus route to a detected bus. OCR failures stay local."""

from __future__ import annotations

import math

import numpy as np

from pipeline.bus_route.ocr_reader import BusOcrReader, OcrText
from pipeline.bus_route.route_matcher import (
    RouteMatch,
    RouteStabilityTracker,
    interpret_ocr_evidence,
)

_OCR_INTERVAL_FRAMES = 6
_MIN_CROP_WIDTH = 120
_MIN_CROP_HEIGHT = 40


def clamp_bbox(
    bbox_xyxy: tuple[float, float, float, float],
    width: int,
    height: int,
) -> tuple[int, int, int, int] | None:
    """Clamp a box to the frame. Return None when the overlap is empty."""
    x1, y1, x2, y2 = bbox_xyxy
    left = max(0, min(width, math.floor(float(x1))))
    top = max(0, min(height, math.floor(float(y1))))
    right = max(0, min(width, math.ceil(float(x2))))
    bottom = max(0, min(height, math.ceil(float(y2))))
    if right <= left or bottom <= top:
        return None
    return left, top, right, bottom


def crop_bus(
    frame_bgr: np.ndarray,
    bbox_xyxy: tuple[float, float, float, float],
    min_width: int = _MIN_CROP_WIDTH,
    min_height: int = _MIN_CROP_HEIGHT,
) -> np.ndarray | None:
    """Return a clamped bus crop, or None when it is empty or too small."""
    if frame_bgr is None or frame_bgr.ndim < 2 or frame_bgr.size == 0:
        return None
    height, width = int(frame_bgr.shape[0]), int(frame_bgr.shape[1])
    clamped = clamp_bbox(bbox_xyxy, width, height)
    if clamped is None:
        return None
    left, top, right, bottom = clamped
    if (right - left) < min_width or (bottom - top) < min_height:
        return None
    return np.ascontiguousarray(frame_bgr[top:bottom, left:right])


def _box_area(bbox_xyxy) -> float:
    try:
        x1, y1, x2, y2 = bbox_xyxy
        return max(0.0, float(x2) - float(x1)) * max(0.0, float(y2) - float(y1))
    except (TypeError, ValueError):
        return -1.0


def ocr_evidence_texts(items: list[OcrText], combined: str) -> list[str]:
    """Keep every OCR line from the crop, plus the joined reading-order string."""
    texts = [item.text for item in items if item.text and item.text.strip()]
    if combined and combined.strip() and combined not in texts:
        texts.append(combined)
    return texts


def select_route_match(items: list[OcrText], combined: str) -> RouteMatch | None:
    """Apply the production route rules to one bus crop. Ambiguity returns None."""
    return interpret_ocr_evidence(ocr_evidence_texts(items, combined)).match


def _clear_route_fields(obj) -> None:
    obj.route_line = None
    obj.route_code = None
    obj.route_destination = None
    obj.route_direction = None
    obj.route_confidence = None
    obj.route_is_stable = False
    obj.route_tts_message = None


class BusRouteIdentifier:
    """OCR at most one bus crop every few frames, and publish only a stable route."""

    def __init__(
        self,
        reader: BusOcrReader | None = None,
        tracker: RouteStabilityTracker | None = None,
        ocr_interval: int = _OCR_INTERVAL_FRAMES,
    ):
        self.reader = reader if reader is not None else BusOcrReader()
        self.tracker = tracker if tracker is not None else RouteStabilityTracker()
        self.ocr_interval = ocr_interval
        self._last_ocr_frame: dict[int, int] = {}

    def apply(self, frame_bgr: np.ndarray, objects: list, frame_index: int) -> None:
        """Update route fields on `objects`. An OCR failure does not stop the frame."""
        try:
            self._apply(frame_bgr, objects, frame_index)
        except Exception:
            return

    def _apply(self, frame_bgr: np.ndarray, objects: list, frame_index: int) -> None:
        buses = [obj for obj in objects if getattr(obj, "class_name", "") == "bus"]
        live_ids = {obj.track_id for obj in buses}
        self.tracker.clear_inactive(active_track_ids=live_ids)
        for track_id in list(self._last_ocr_frame):
            if track_id not in live_ids:
                del self._last_ocr_frame[track_id]

        target = max(buses, key=lambda obj: _box_area(obj.bbox_xyxy), default=None)
        if target is not None and self._ocr_due(target.track_id, frame_index):
            self._read_bus(frame_bgr, target, frame_index)

        for obj in objects:
            _clear_route_fields(obj)
        for bus in buses:
            stable = self.tracker.get_stable(bus.track_id)
            if stable is not None:
                self._assign(bus, stable)

    def _ocr_due(self, track_id: int, frame_index: int) -> bool:
        last = self._last_ocr_frame.get(track_id)
        if last is None:
            return True
        return frame_index - last >= self.ocr_interval

    def _read_bus(self, frame_bgr: np.ndarray, bus, frame_index: int) -> None:
        crop = crop_bus(frame_bgr, bus.bbox_xyxy)
        if crop is None:
            return
        self._last_ocr_frame[bus.track_id] = frame_index
        try:
            items, combined = self.reader.text_candidates(crop)
            match = select_route_match(items, combined)
            self.tracker.observe(bus.track_id, match)
        except Exception:
            return

    def _assign(self, bus, match: RouteMatch) -> None:
        bus.route_line = match.route_line
        bus.route_code = match.route_code
        bus.route_destination = match.route_destination
        bus.route_direction = match.direction_id
        bus.route_confidence = match.confidence
        bus.route_is_stable = True
        bus.route_tts_message = match.tts_message
