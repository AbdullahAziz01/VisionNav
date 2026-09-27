import sys
import unittest
from unittest.mock import MagicMock, patch

import numpy as np

from pipeline.bus_route.identifier import BusRouteIdentifier, crop_bus
from pipeline.bus_route.ocr_reader import OcrText
from pipeline.models import ObjectDistance


class FakeOcr:
    """Stand-in for BusOcrReader. Does not import or construct EasyOCR."""

    def __init__(self, texts: list[str]):
        self.texts = texts
        self.images: list[np.ndarray] = []

    def text_candidates(self, image_bgr):
        self.images.append(np.ascontiguousarray(image_bgr))
        items = [
            OcrText(
                text=text,
                confidence=0.95,
                bbox=((0.0, float(index)), (10.0, float(index)), (10.0, float(index) + 8), (0.0, float(index) + 8)),
            )
            for index, text in enumerate(self.texts)
        ]
        combined = " ".join(item.text for item in items)
        return items, combined


class FailingOcr:
    def text_candidates(self, image_bgr):
        raise RuntimeError("ocr failed")


def _detection(class_name="bus", track_id=4, bbox=(10, 20, 220, 140)):
    return ObjectDistance(
        track_id=track_id,
        class_name=class_name,
        confidence=0.85,
        bbox_xyxy=bbox,
        estimated_distance_m=12.0,
        raw_depth_value=12.0,
        is_metric=True,
        distance_label="12.0 m (estimated metric)",
        depth_backend="test",
        tracking_backend="bytetrack",
    )


def _frame(height=240, width=320) -> np.ndarray:
    return np.zeros((height, width, 3), dtype=np.uint8)


class TestBusRouteIdentifier(unittest.TestCase):
    def test_no_ocr_when_no_bus(self):
        reader = FakeOcr(["BARAKAHU"])
        identifier = BusRouteIdentifier(reader=reader)
        person = _detection(class_name="person", track_id=1)
        identifier.apply(_frame(), [person], frame_index=1)

        self.assertEqual(reader.images, [])
        self.assertIsNone(person.route_line)
        self.assertIsNone(person.route_destination)
        self.assertIsNone(person.route_direction)
        self.assertIsNone(person.route_confidence)
        self.assertFalse(person.route_is_stable)
        self.assertIsNone(person.route_tts_message)

    def test_crop_is_clamped_safely(self):
        frame = _frame(height=200, width=300)
        frame[0, 0] = (9, 8, 7)
        frame[79, 299] = (1, 2, 3)
        reader = FakeOcr(["BARAKAHU"])
        identifier = BusRouteIdentifier(reader=reader)
        bus = _detection(bbox=(-40, -15, 500, 80))

        identifier.apply(frame, [bus], frame_index=1)

        self.assertEqual(len(reader.images), 1)
        crop = reader.images[0]
        self.assertEqual(crop.shape, (80, 300, 3))
        self.assertLessEqual(crop.shape[0], frame.shape[0])
        self.assertLessEqual(crop.shape[1], frame.shape[1])
        np.testing.assert_array_equal(crop, frame[0:80, 0:300])

        tiny = _detection(track_id=9, bbox=(0, 0, 80, 30))
        skipped = FakeOcr(["BARAKAHU"])
        BusRouteIdentifier(reader=skipped).apply(_frame(), [tiny], frame_index=1)
        self.assertEqual(skipped.images, [])
        self.assertIsNone(crop_bus(_frame(), tiny.bbox_xyxy))

    def test_stable_barakahu_returns_green_line(self):
        fake_easyocr = MagicMock()
        reader = FakeOcr(["BARAKAHU"])
        with patch.dict(sys.modules, {"easyocr": fake_easyocr}):
            identifier = BusRouteIdentifier(reader=reader)
            bus = _detection(track_id=7)
            frame = _frame()
            for frame_index in (1, 2, 7):
                identifier.apply(frame, [bus], frame_index)

            self.assertFalse(bus.route_is_stable)
            self.assertIsNone(bus.route_line)
            self.assertEqual(len(reader.images), 2)

            identifier.apply(frame, [bus], frame_index=13)

        fake_easyocr.Reader.assert_not_called()
        self.assertEqual(len(reader.images), 3)
        self.assertEqual(bus.route_line, "Green Line")
        self.assertEqual(bus.route_destination, "Barakahu")
        self.assertEqual(bus.route_direction, "toward_barakahu")
        self.assertEqual(bus.route_confidence, 1.0)
        self.assertTrue(bus.route_is_stable)
        self.assertEqual(bus.route_tts_message, "Green Line toward Barakahu.")

    def test_stable_n5_returns_orange_line(self):
        reader = FakeOcr(["N-5"])
        identifier = BusRouteIdentifier(reader=reader)
        bus = _detection(track_id=8)
        frame = _frame()
        for frame_index in (1, 7, 13):
            identifier.apply(frame, [bus], frame_index)

        self.assertEqual(bus.route_line, "Orange Line")
        self.assertEqual(bus.route_destination, "N-5")
        self.assertEqual(bus.route_direction, "toward_n5")
        self.assertEqual(bus.route_confidence, 1.0)
        self.assertTrue(bus.route_is_stable)
        self.assertEqual(bus.route_tts_message, "Orange Line toward N-5.")

    def test_pims_without_green_does_not_announce(self):
        reader = FakeOcr(["PIMS"])
        identifier = BusRouteIdentifier(reader=reader)
        bus = _detection()
        frame = _frame()
        for frame_index in (1, 7, 13):
            identifier.apply(frame, [bus], frame_index)

        self.assertEqual(len(reader.images), 3)
        self.assertIsNone(bus.route_line)
        self.assertIsNone(bus.route_destination)
        self.assertIsNone(bus.route_direction)
        self.assertIsNone(bus.route_confidence)
        self.assertFalse(bus.route_is_stable)
        self.assertIsNone(bus.route_tts_message)

    def test_pims_with_green_can_become_stable(self):
        reader = FakeOcr(["GREEN LINE", "PIMS"])
        identifier = BusRouteIdentifier(reader=reader)
        bus = _detection()
        frame = _frame()
        for frame_index in (1, 7, 13):
            identifier.apply(frame, [bus], frame_index)

        self.assertEqual(bus.route_line, "Green Line")
        self.assertEqual(bus.route_direction, "toward_pims")
        self.assertEqual(bus.route_destination, "PIMS Hospital")
        self.assertTrue(bus.route_is_stable)
        self.assertEqual(bus.route_tts_message, "Green Line toward PIMS Hospital.")

    def test_ocr_error_does_not_break_frame_processing(self):
        identifier = BusRouteIdentifier(reader=FailingOcr())
        bus = _detection()
        person = _detection(class_name="person", track_id=2, bbox=(0, 0, 40, 40))
        identifier.apply(_frame(), [person, bus], frame_index=1)

        self.assertFalse(bus.route_is_stable)
        self.assertIsNone(bus.route_line)
        self.assertFalse(person.route_is_stable)
        self.assertIsNone(person.route_tts_message)

    def test_only_largest_bus_is_read(self):
        reader = FakeOcr(["BARAKAHU"])
        identifier = BusRouteIdentifier(reader=reader)
        frame = _frame(height=240, width=400)
        small = _detection(track_id=1, bbox=(0, 0, 130, 50))
        large = _detection(track_id=2, bbox=(0, 0, 300, 200))
        identifier.apply(frame, [small, large], frame_index=1)

        self.assertEqual(len(reader.images), 1)
        self.assertEqual(reader.images[0].shape, (200, 300, 3))


if __name__ == "__main__":
    unittest.main()
