"""Read destination text from a bus crop. EasyOCR loads only on the first call."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

_MIN_CONFIDENCE = 0.35


@dataclass(frozen=True)
class OcrText:
    text: str
    confidence: float
    bbox: tuple[tuple[float, float], ...]


def bgr_to_rgb(image_bgr: np.ndarray) -> np.ndarray:
    """Swap OpenCV BGR channels to RGB. Does not touch EasyOCR."""
    if image_bgr.ndim != 3 or image_bgr.shape[2] != 3:
        raise ValueError("Expected a BGR image with shape (H, W, 3)")
    return np.ascontiguousarray(image_bgr[:, :, ::-1])


def _as_bbox(raw_bbox) -> tuple[tuple[float, float], ...]:
    return tuple((float(point[0]), float(point[1])) for point in raw_bbox)


def _reading_order_key(item: OcrText) -> tuple[float, float]:
    if not item.bbox:
        return (0.0, 0.0)
    return (min(point[1] for point in item.bbox), min(point[0] for point in item.bbox))


class BusOcrReader:
    """EasyOCR wrapper. Constructing it does not download or load weights."""

    def __init__(
        self,
        languages: tuple[str, ...] = ("en",),
        gpu: bool = False,
        min_confidence: float = _MIN_CONFIDENCE,
    ):
        self._languages = list(languages)
        self._gpu = gpu
        self._min_confidence = min_confidence
        self._reader = None

    def _ensure_reader(self):
        if self._reader is None:
            import easyocr

            self._reader = easyocr.Reader(self._languages, gpu=self._gpu)
        return self._reader

    def read_text(self, image_bgr: np.ndarray) -> list[OcrText]:
        """Return recognized lines at or above the confidence floor."""
        rgb = bgr_to_rgb(image_bgr)
        raw_items = self._ensure_reader().readtext(rgb)
        kept: list[OcrText] = []
        for raw in raw_items:
            bbox, text, confidence = raw[0], raw[1], float(raw[2])
            cleaned = str(text).strip()
            if not cleaned or confidence < self._min_confidence:
                continue
            kept.append(
                OcrText(
                    text=cleaned,
                    confidence=confidence,
                    bbox=_as_bbox(bbox),
                )
            )
        return kept

    def text_candidates(self, image_bgr: np.ndarray) -> tuple[list[OcrText], str]:
        """Return kept OCR items and one string joined in reading order."""
        items = sorted(self.read_text(image_bgr), key=_reading_order_key)
        combined = " ".join(item.text for item in items)
        return items, combined
