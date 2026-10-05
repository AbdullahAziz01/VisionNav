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

    def test_stable_barakahu_stop_returns_green_line(self):
        fake_easyocr = MagicMock()
        reader = FakeOcr(["BARAKAHU STOP"])
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
        self.assertIsNone(bus.route_code)

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

    def test_green_and_pims_do_not_identify_a_route(self):
        reader = FakeOcr(["GREEN LINE", "PIMS"])
        identifier = BusRouteIdentifier(reader=reader)
        bus = _detection()
        frame = _frame()
        for frame_index in (1, 7, 13):
            identifier.apply(frame, [bus], frame_index)

        self.assertEqual(len(reader.images), 3)
        self.assertIsNone(bus.route_line)
        self.assertIsNone(bus.route_code)
        self.assertIsNone(bus.route_direction)
        self.assertFalse(bus.route_is_stable)
        self.assertIsNone(bus.route_tts_message)

    def test_pims_hospital_can_become_stable(self):
        reader = FakeOcr(["PIMS HOSPITAL"])
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


class ScriptedOcr:
    def __init__(self, scripts: list[list[str]]):
        self.scripts = scripts
        self.calls = 0

    def text_candidates(self, image_bgr):
        texts = self.scripts[min(self.calls, len(self.scripts) - 1)]
        self.calls += 1
        items = [
            OcrText(text=text, confidence=0.95, bbox=((0.0, 0.0),))
            for text in texts
        ]
        return items, " ".join(texts)


def _stabilize(identifier, bus, frame, count, start_step=0):
    for step in range(start_step, start_step + count):
        identifier.apply(frame, [bus], frame_index=1 + step * 6)


class TestFeederRoutePipeline(unittest.TestCase):
    def test_code_only_becomes_stable_without_a_direction(self):
        identifier = BusRouteIdentifier(reader=FakeOcr(["FR-7"]))
        bus = _detection()
        frame = _frame()
        _stabilize(identifier, bus, frame, 3)

        self.assertEqual(bus.route_code, "FR-7")
        self.assertEqual(bus.route_line, "FR-7")
        self.assertIsNone(bus.route_direction)
        self.assertIsNone(bus.route_destination)
        self.assertTrue(bus.route_is_stable)
        self.assertEqual(
            bus.route_tts_message,
            "Feeder route seven detected. Direction could not be read.",
        )

    def test_later_direction_replaces_route_only(self):
        reader = ScriptedOcr(
            [["FR-7"], ["FR-7"], ["FR-7"], ["FR-7", "G-11"], ["FR-7", "G-11"], ["FR-7", "G-11"]]
        )
        identifier = BusRouteIdentifier(reader=reader)
        bus = _detection()
        frame = _frame()
        _stabilize(identifier, bus, frame, 3)
        self.assertIsNone(bus.route_direction)

        _stabilize(identifier, bus, frame, 3, start_step=3)
        self.assertEqual(bus.route_code, "FR-7")
        self.assertEqual(bus.route_direction, "fr_7_toward_g11")
        self.assertEqual(bus.route_destination, "G-11")
        self.assertEqual(bus.route_tts_message, "Feeder route seven toward G-11.")

    def test_both_endpoints_do_not_assign_a_direction(self):
        identifier = BusRouteIdentifier(reader=FakeOcr(["PIMS", "G-11"]))
        bus = _detection()
        _stabilize(identifier, bus, _frame(), 3)

        self.assertEqual(bus.route_code, "FR-7")
        self.assertIsNone(bus.route_direction)
        self.assertIsNone(bus.route_destination)
        self.assertEqual(
            bus.route_tts_message,
            "Feeder route seven detected. Direction could not be read.",
        )

    def test_stale_direction_is_replaced_by_contradictory_reads(self):
        reader = ScriptedOcr(
            [
                ["FR-7", "G-11"],
                ["FR-7", "G-11"],
                ["FR-7", "G-11"],
                ["FR-7", "PIMS"],
                ["FR-7", "PIMS"],
                ["FR-7", "PIMS"],
            ]
        )
        identifier = BusRouteIdentifier(reader=reader)
        bus = _detection()
        frame = _frame()
        _stabilize(identifier, bus, frame, 5)
        self.assertEqual(bus.route_direction, "fr_7_toward_g11")

        identifier.apply(frame, [bus], frame_index=1 + 5 * 6)
        self.assertEqual(bus.route_direction, "fr_7_toward_pims")
        self.assertEqual(bus.route_destination, "PIMS")
        self.assertEqual(bus.route_tts_message, "Feeder route seven toward PIMS.")

    def test_conflicting_reads_clear_a_stale_direction(self):
        reader = ScriptedOcr(
            [
                ["FR-7", "G-11"],
                ["FR-7", "G-11"],
                ["FR-7", "G-11"],
                ["FR-7", "TAXILA"],
                ["FR-7", "TAXILA"],
                ["FR-7", "TAXILA"],
            ]
        )
        identifier = BusRouteIdentifier(reader=reader)
        bus = _detection()
        frame = _frame()
        _stabilize(identifier, bus, frame, 5)
        self.assertEqual(bus.route_direction, "fr_7_toward_g11")

        identifier.apply(frame, [bus], frame_index=1 + 5 * 6)
        self.assertFalse(bus.route_is_stable)
        self.assertIsNone(bus.route_direction)
        self.assertIsNone(bus.route_tts_message)
        self.assertIsNone(bus.route_code)

    def test_ocr_exception_after_a_stable_route_does_not_break_the_frame(self):
        class ThenFail:
            def __init__(self):
                self.calls = 0

            def text_candidates(self, image_bgr):
                self.calls += 1
                if self.calls > 3:
                    raise RuntimeError("ocr failed")
                return [OcrText(text="N-5", confidence=0.9, bbox=())], "N-5"

        identifier = BusRouteIdentifier(reader=ThenFail())
        bus = _detection()
        frame = _frame()
        _stabilize(identifier, bus, frame, 3)
        self.assertEqual(bus.route_tts_message, "Orange Line toward N-5.")

        identifier.apply(frame, [bus], frame_index=1 + 3 * 6)
        self.assertEqual(bus.route_line, "Orange Line")
        self.assertEqual(bus.route_tts_message, "Orange Line toward N-5.")
        self.assertTrue(bus.route_is_stable)


if __name__ == "__main__":
    unittest.main()
