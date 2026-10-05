import json
import unittest
from pathlib import Path

from pipeline.bus_route.ocr_reader import OcrText
from pipeline.bus_route.identifier import select_route_match
from pipeline.bus_route.route_matcher import (
    format_route_interpretation,
    interpret_ocr_evidence,
    match_route_text,
)

ROOT = Path(__file__).resolve().parents[1]
ROUTES_PATH = ROOT / "pipeline" / "bus_route" / "routes.json"
SNAPSHOT_PATH = ROOT / "docs" / "feeder_routes_source_snapshot_2026-10-05.json"

EXPECTED_CODES = [
    "FR-1",
    "FR-2",
    "FR-3A",
    "FR-04",
    "FR-4",
    "FR-4A",
    "FR-6",
    "FR-7",
    "FR-8A",
    "FR-8B",
    "FR-8C",
    "FR-9",
    "FR-10",
    "FR-11",
    "FR-12",
    "FR-13",
    "FR-14",
    "FR-14A",
    "FR-15",
    "EXP-16",
    "FR-17",
    "FRG-01",
]

ROUTE_ONLY_SPEECH = {
    "FR-1": "Feeder route one detected. Direction could not be read.",
    "FR-2": "Feeder route two detected. Direction could not be read.",
    "FR-3A": "Feeder route three A detected. Direction could not be read.",
    "FR-04": "Feeder route zero four detected. Direction could not be read.",
    "FR-4": "Feeder route four detected. Direction could not be read.",
    "FR-4A": "Feeder route four A detected. Direction could not be read.",
    "FR-6": "Feeder route six detected. Direction could not be read.",
    "FR-7": "Feeder route seven detected. Direction could not be read.",
    "FR-8A": "Feeder route eight A detected. Direction could not be read.",
    "FR-8B": "Feeder route eight B detected. Direction could not be read.",
    "FR-8C": "Feeder route eight C detected. Direction could not be read.",
    "FR-9": "Feeder route nine detected. Direction could not be read.",
    "FR-10": "Feeder route ten detected. Direction could not be read.",
    "FR-11": "Feeder route eleven detected. Direction could not be read.",
    "FR-12": "Feeder route twelve detected. Direction could not be read.",
    "FR-13": "Feeder route thirteen detected. Direction could not be read.",
    "FR-14": "Feeder route fourteen detected. Direction could not be read.",
    "FR-14A": "Feeder route fourteen A detected. Direction could not be read.",
    "FR-15": "Feeder route fifteen detected. Direction could not be read.",
    "EXP-16": "Express route sixteen detected. Direction could not be read.",
    "FR-17": "Feeder route seventeen detected. Direction could not be read.",
    "FRG-01": "Feeder route G zero one detected. Direction could not be read.",
}

DIRECTED_SPEECH = {
    ("FR-7", "G-11"): "Feeder route seven toward G-11.",
    ("FR-8A", "Aabpara"): "Feeder route eight A toward Tramri.",
    ("FR-8B", "Nilore"): "Feeder route eight B toward Nilore.",
    ("FR-8C", "Tramri Faizabad"): "Feeder route eight C toward Tramri Faizabad.",
    ("EXP-16", "Media Town"): "Express route sixteen toward Media Town.",
    ("FRG-01", "BaraKahu"): "Feeder route G zero one toward Barakahu.",
    ("FR-04", "Bari Imam"): "Feeder route zero four toward Bari Imam.",
    ("FR-4", "Aiwan e Saddar"): "Feeder route four toward Aiwan e Saddar.",
}


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class TestFeederRouteDatabase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = _load(ROUTES_PATH)
        cls.snapshot = _load(SNAPSHOT_PATH)
        cls.by_code = {
            route["route_code"]: route
            for route in cls.payload["routes"]
            if route.get("route_code")
        }

    def test_snapshot_counts_and_catalog(self):
        self.assertEqual(len(self.snapshot["routes"]), 22)
        self.assertEqual(list(self.by_code), EXPECTED_CODES)
        self.assertEqual(
            self.payload["source_url"],
            "https://metro-status.com/feeder-metro/",
        )
        for route in self.by_code.values():
            self.assertNotIn("website_status", route)
            self.assertNotIn("source_service_note", route)
        stored = json.dumps(self.by_code)
        self.assertNotIn("Trial Phase", stored)
        self.assertNotIn("Every ", stored)

    def test_substation_lists_match_the_snapshot(self):
        with_stops = []
        without_stops = []
        for source in self.snapshot["routes"]:
            route = self.by_code[source["route_code"]]
            self.assertEqual(route["source_title"], source["source_title"])
            self.assertEqual(route["source_url"], self.snapshot["source_url"])
            self.assertTrue(route["aliases_are_recognition_only"])
            for issue in source.get("issues") or []:
                self.assertIn(issue, route["source_uncertainty_notes"])
            if source["stops"]:
                with_stops.append(source["route_code"])
                self.assertTrue(route["substations_available"])
                self.assertEqual(route["substations"], source["stops"])
            else:
                without_stops.append(source["route_code"])
                self.assertFalse(route["substations_available"])
                self.assertIsNone(route["substations"])
        self.assertEqual(with_stops, ["FR-1", "FR-3A", "FR-4", "FR-4A", "FR-7"])
        self.assertEqual(len(without_stops), 17)

    def test_corridor_endpoints_are_not_replaced_by_stop_lists(self):
        fr1 = self.by_code["FR-1"]
        self.assertEqual(fr1["corridor_endpoints"], ["Khanna Pul", "NUST Metro Station"])
        self.assertEqual(fr1["substations"][0], "Nust Metro Station")
        self.assertEqual(fr1["substations"][-1], "Khanna Pul")
        self.assertEqual(fr1["substations"].count("Iqbal Town"), 2)

        fr3a = self.by_code["FR-3A"]
        self.assertEqual(fr3a["corridor_endpoints"], ["PIMS", "Faisal Masjid"])
        self.assertEqual(fr3a["substations"][-1], "Said Pur Village")

        fr4a = self.by_code["FR-4A"]
        self.assertEqual(fr4a["corridor_endpoints"], ["PIMS", "QAU"])
        self.assertEqual(fr4a["substations"][0], "Bari Imam")

        fr7 = self.by_code["FR-7"]
        self.assertEqual(fr7["corridor_endpoints"], ["PIMS", "G-11"])
        self.assertEqual(fr7["substations"][-1], "Police Foundation Metro Station")

        self.assertIn("FR-04", self.by_code)
        self.assertIn("FR-4", self.by_code)
        self.assertNotEqual(
            self.by_code["FR-04"]["source_title"],
            self.by_code["FR-4"]["source_title"],
        )

    def test_stored_code_aliases_do_not_include_the_fr4_collision(self):
        for route in self.by_code.values():
            self.assertNotIn("FR4", route["ocr_code_aliases"])
            for alias in route["ocr_code_aliases"]:
                match = match_route_text(alias)
                self.assertIsNotNone(match, alias)
                self.assertEqual(match.route_code, route["route_code"])
                self.assertIsNone(match.direction_id)

    def test_every_route_has_route_only_speech_and_no_service_claims(self):
        for code, speech in ROUTE_ONLY_SPEECH.items():
            route = self.by_code[code]
            self.assertEqual(route["route_only_tts"], speech)
            blob = json.dumps(route)
            self.assertNotIn("board", blob.lower())
            for direction in route["directions"]:
                self.assertEqual(direction["alias_role"], "recognition")
                self.assertNotIn("could not be read", direction["tts_message"])
                self.assertIn("toward", direction["tts_message"])
            self.assertNotIn("toward", route["route_only_tts"])


class TestFeederRecognition(unittest.TestCase):
    def test_code_formatting_and_suffixes(self):
        cases = {
            "FR-7": "FR-7",
            "FR7": "FR-7",
            "FR 7": "FR-7",
            "FR-8A": "FR-8A",
            "FR8A": "FR-8A",
            "FR 8 A": "FR-8A",
            "FR-8B": "FR-8B",
            "FR-8C": "FR-8C",
            "EXP-16": "EXP-16",
            "EXP16": "EXP-16",
            "EXP 16": "EXP-16",
            "FRG-01": "FRG-01",
            "FRG01": "FRG-01",
            "FRG 1": "FRG-01",
            "FR-14A": "FR-14A",
            "FR14A": "FR-14A",
        }
        for text, code in cases.items():
            match = match_route_text(text)
            self.assertIsNotNone(match, text)
            self.assertEqual(match.route_code, code, text)
            self.assertIsNone(match.direction_id, text)
            self.assertEqual(match.tts_message, ROUTE_ONLY_SPEECH[code])

    def test_longer_codes_do_not_match_shorter_prefixes(self):
        for text, code in {
            "FR-10": "FR-10",
            "FR10": "FR-10",
            "FR-11": "FR-11",
            "FR-12": "FR-12",
            "FR-14": "FR-14",
            "FR-15": "FR-15",
            "FR-17": "FR-17",
        }.items():
            match = match_route_text(text)
            self.assertEqual(match.route_code, code)
            self.assertNotEqual(match.route_code, "FR-1")
        self.assertIsNone(match_route_text("FR-8"))
        self.assertIsNone(match_route_text("FR-3"))
        self.assertIsNone(match_route_text("FROM 7"))
        self.assertIsNone(match_route_text("AFR-7"))

    def test_fr4_does_not_choose_between_fr4_and_fr04(self):
        ambiguous = interpret_ocr_evidence(["FR4"])
        self.assertTrue(ambiguous.ambiguous)
        self.assertIsNone(ambiguous.match)
        self.assertIsNone(ambiguous.speech)

        for text, code in {"FR-4": "FR-4", "FR 4": "FR-4", "FR-04": "FR-04", "FR04": "FR-04", "FR 04": "FR-04"}.items():
            match = match_route_text(text)
            self.assertEqual(match.route_code, code, text)

        kept = match_route_text("FR-4 FR4")
        self.assertEqual(kept.route_code, "FR-4")
        conflict = interpret_ocr_evidence(["FR-7 FR4"])
        self.assertEqual(conflict.status, "conflict")
        self.assertIsNone(conflict.match)

    def test_directed_speech(self):
        for (code, destination), speech in DIRECTED_SPEECH.items():
            match = match_route_text(f"{code} {destination}")
            self.assertIsNotNone(match, f"{code} {destination}")
            self.assertEqual(match.route_code, code)
            self.assertIsNotNone(match.direction_id)
            self.assertEqual(match.tts_message, speech)

    def test_shared_destinations_do_not_pick_the_first_route(self):
        for text in ("PIMS", "Barakahu", "Bara Kahu", "Tramri", "Tramari", "Khanna Pul", "Golra Mor", "Golra Morh", "Taxila", "GREEN LINE PIMS"):
            result = interpret_ocr_evidence([text])
            self.assertTrue(result.ambiguous, text)
            self.assertIsNone(result.match, text)

        self.assertEqual(match_route_text("N-5").route_line, "Orange Line")
        self.assertEqual(match_route_text("Faiz Ahmad Faiz").route_destination, "Faiz Ahmad Faiz")
        self.assertEqual(match_route_text("PIMS HOSPITAL").route_line, "Green Line")
        self.assertEqual(match_route_text("BARAKAHU STOP").direction_id, "toward_barakahu")
        self.assertEqual(match_route_text("Bahra Kahu").route_code, "FR-14")
        self.assertEqual(match_route_text("Bhara Khu").route_code, "FR-15")

    def test_tramri_alone_does_not_choose_fr8a_or_fr8c(self):
        self.assertIsNone(match_route_text("Tramri"))
        toward_a = match_route_text("FR-8A Tramri")
        toward_c = match_route_text("FR-8C Tramri")
        self.assertEqual(toward_a.route_code, "FR-8A")
        self.assertEqual(toward_a.route_destination, "Tramri")
        self.assertEqual(toward_c.route_code, "FR-8C")
        self.assertEqual(toward_c.route_destination, "Tramri Faizabad")
        self.assertEqual(match_route_text("Aabpara").route_code, "FR-8A")
        self.assertEqual(match_route_text("Abpara").route_code, "FR-8A")

    def test_both_endpoints_do_not_establish_direction(self):
        match = match_route_text("PIMS G-11")
        self.assertEqual(match.route_code, "FR-7")
        self.assertIsNone(match.direction_id)
        self.assertIsNone(match.route_destination)
        self.assertEqual(match.tts_message, ROUTE_ONLY_SPEECH["FR-7"])

        both_green = match_route_text("PIMS HOSPITAL BARAKAHU STOP")
        self.assertEqual(both_green.route_line, "Green Line")
        self.assertIsNone(both_green.direction_id)
        self.assertEqual(
            both_green.tts_message,
            "Green Line detected. Direction could not be read.",
        )

        fr10 = match_route_text("Golra Mor Taxila")
        self.assertEqual(fr10.route_code, "FR-10")
        self.assertIsNone(fr10.direction_id)

    def test_intermediate_substations_are_not_destinations(self):
        for text in (
            "G-9 Markaz",
            "G-11 Markaz",
            "Said Pur Village",
            "Police Foundation Metro Station",
            "Faizabad Metro Station",
            "Abpara Market",
            "Aiwan e Sadar Colony",
            "Iqbal Town",
        ):
            self.assertIsNone(match_route_text(text), text)

        colony = match_route_text("FR-4 Aiwan e Sadar Colony")
        self.assertEqual(colony.route_code, "FR-4")
        self.assertIsNone(colony.direction_id)

    def test_split_ocr_lines_keep_all_evidence(self):
        items = [
            OcrText(text="FR", confidence=0.9, bbox=()),
            OcrText(text="8 A", confidence=0.9, bbox=()),
        ]
        match = select_route_match(items, "FR 8 A")
        self.assertEqual(match.route_code, "FR-8A")

        conflict = select_route_match(
            [
                OcrText(text="FR-7", confidence=0.9, bbox=()),
                OcrText(text="FR-10", confidence=0.9, bbox=()),
            ],
            "FR-7 FR-10",
        )
        self.assertIsNone(conflict)

    def test_distinctive_endpoints_and_qau_alias(self):
        self.assertEqual(match_route_text("Faisal Masjid").route_code, "FR-3A")
        self.assertEqual(match_route_text("Faisal Masjid").route_destination, "Faisal Masjid")
        self.assertIsNone(match_route_text("Said Pur Village"))
        self.assertEqual(match_route_text("QAU").route_destination, "QAU")
        self.assertEqual(match_route_text("Quaid Azam University").route_code, "FR-4A")
        self.assertEqual(match_route_text("Bari Imam").route_code, "FR-04")
        self.assertNotEqual(match_route_text("Bari Imam").route_code, "FR-4")
        self.assertEqual(match_route_text("Golra Shareef").route_code, "FR-6")
        self.assertEqual(match_route_text("G11").route_code, "FR-7")
        self.assertEqual(match_route_text("G 11").route_destination, "G-11")

    def test_production_report_includes_code_direction_ambiguity_and_speech(self):
        report = format_route_interpretation(interpret_ocr_evidence(["FR-7", "G-11"]))
        self.assertIn("Matched code: FR-7", report)
        self.assertIn("Direction known: yes", report)
        self.assertIn("Ambiguous: no", report)
        self.assertIn("Speech: Feeder route seven toward G-11.", report)

        unknown = format_route_interpretation(interpret_ocr_evidence(["FR-7"]))
        self.assertIn("Direction: (unknown)", unknown)
        self.assertIn("Direction known: no", unknown)
        self.assertIn("Feeder route seven detected. Direction could not be read.", unknown)

        ambiguous = format_route_interpretation(interpret_ocr_evidence(["Tramri"]))
        self.assertIn("Matched code: (none)", ambiguous)
        self.assertIn("Ambiguous: yes", ambiguous)
        self.assertIn("Speech: (none)", ambiguous)

        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "test_bus_route_ocr",
            ROOT / "tools" / "test_bus_route_ocr.py",
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertEqual(
            module.describe_ocr_texts(["FR-7", "G-11"]),
            report,
        )


if __name__ == "__main__":
    unittest.main()
