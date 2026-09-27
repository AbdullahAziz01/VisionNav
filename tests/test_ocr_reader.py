import importlib
import sys
import unittest
from unittest.mock import MagicMock, patch

import numpy as np

from pipeline.bus_route.ocr_reader import BusOcrReader


def _bgr_image() -> np.ndarray:
    image = np.zeros((4, 4, 3), dtype=np.uint8)
    image[0, 0] = (10, 20, 30)  # B, G, R
    return image


def _box(x: float, y: float):
    return [[x, y], [x + 10, y], [x + 10, y + 8], [x, y + 8]]


class TestOcrReader(unittest.TestCase):
    def test_import_does_not_initialize_easyocr_reader(self):
        sys.modules.pop("pipeline.bus_route.ocr_reader", None)
        fake_easyocr = MagicMock()
        with patch.dict(sys.modules, {"easyocr": fake_easyocr}):
            imported = importlib.import_module("pipeline.bus_route.ocr_reader")
            importlib.reload(imported)
            fake_easyocr.Reader.assert_not_called()
            reader = imported.BusOcrReader()
            self.assertIsNone(reader._reader)
            fake_easyocr.Reader.assert_not_called()

    def test_bgr_to_rgb_and_confidence_filter(self):
        fake_easyocr = MagicMock()
        fake_instance = MagicMock()
        fake_easyocr.Reader.return_value = fake_instance
        fake_instance.readtext.return_value = [
            (_box(0, 40), "BARAKAHU", 0.91),
            (_box(0, 0), "   ", 0.99),
            (_box(0, 0), "", 0.80),
            (_box(20, 40), "NOISE", 0.34),
            (_box(0, 10), "PIMS", 0.35),
        ]

        with patch.dict(sys.modules, {"easyocr": fake_easyocr}):
            reader = BusOcrReader()
            items = reader.read_text(_bgr_image())

        fake_easyocr.Reader.assert_called_once_with(["en"], gpu=False)
        passed = fake_instance.readtext.call_args.args[0]
        expected_rgb = np.zeros((4, 4, 3), dtype=np.uint8)
        expected_rgb[0, 0] = (30, 20, 10)
        np.testing.assert_array_equal(passed, expected_rgb)

        self.assertEqual([(item.text, item.confidence) for item in items], [
            ("BARAKAHU", 0.91),
            ("PIMS", 0.35),
        ])

    def test_text_candidates_join_in_reading_order(self):
        fake_easyocr = MagicMock()
        fake_instance = MagicMock()
        fake_easyocr.Reader.return_value = fake_instance
        fake_instance.readtext.return_value = [
            (_box(30, 10), "STOP", 0.80),
            (_box(0, 10), "BARAKAHU", 0.90),
            (_box(0, 40), "LOW", 0.10),
        ]

        with patch.dict(sys.modules, {"easyocr": fake_easyocr}):
            items, combined = BusOcrReader().text_candidates(_bgr_image())

        self.assertEqual([item.text for item in items], ["BARAKAHU", "STOP"])
        self.assertEqual(combined, "BARAKAHU STOP")

    def test_reader_is_created_once(self):
        fake_easyocr = MagicMock()
        fake_easyocr.Reader.return_value.readtext.return_value = []
        with patch.dict(sys.modules, {"easyocr": fake_easyocr}):
            reader = BusOcrReader()
            reader.read_text(_bgr_image())
            reader.read_text(_bgr_image())
        fake_easyocr.Reader.assert_called_once_with(["en"], gpu=False)


if __name__ == "__main__":
    unittest.main()
