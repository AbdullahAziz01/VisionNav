import unittest

from pipeline.bus_route.route_matcher import RouteStabilityTracker, match_route_text


class TestMatchRouteText(unittest.TestCase):
    def test_barakahu_green_line(self):
        match = match_route_text("barakahu")
        self.assertIsNotNone(match)
        self.assertEqual(match.route_line, "Green Line")
        self.assertEqual(match.direction_id, "toward_barakahu")
        self.assertEqual(match.route_destination, "Barakahu")
        self.assertGreaterEqual(match.confidence, 0.7)
        self.assertEqual(match.raw_text, "barakahu")

    def test_pims_hospital_green_line(self):
        match = match_route_text("PIMS Hospital")
        self.assertIsNotNone(match)
        self.assertEqual(match.route_line, "Green Line")
        self.assertEqual(match.direction_id, "toward_pims")
        self.assertEqual(match.route_destination, "PIMS Hospital")

    def test_n5_orange_line(self):
        match = match_route_text("N 5")
        self.assertIsNotNone(match)
        self.assertEqual(match.route_line, "Orange Line")
        self.assertEqual(match.direction_id, "toward_n5")
        self.assertEqual(match.route_destination, "N-5")

    def test_faiz_ahmad_faiz_orange_line(self):
        match = match_route_text("Faiz Ahmad Faiz")
        self.assertIsNotNone(match)
        self.assertEqual(match.route_line, "Orange Line")
        self.assertEqual(match.direction_id, "toward_faiz_ahmad_faiz")
        self.assertEqual(match.route_destination, "Faiz Ahmad Faiz")

    def test_unrelated_text_returns_none(self):
        self.assertIsNone(match_route_text("hello world"))
        self.assertIsNone(match_route_text("person crossing"))
        self.assertIsNone(match_route_text("metro station"))
        self.assertIsNone(match_route_text(""))
        self.assertIsNone(match_route_text("   "))
        self.assertIsNone(match_route_text(None))

    def test_exact_match_outranks_loose_alias(self):
        exact = match_route_text("PIMS HOSPITAL")
        loose = match_route_text("next stop PIMS HOSPITAL please")
        self.assertIsNotNone(exact)
        self.assertIsNotNone(loose)
        self.assertGreater(exact.confidence, loose.confidence)
        self.assertEqual(exact.direction_id, "toward_pims")
        self.assertEqual(loose.direction_id, "toward_pims")


class TestRouteStabilityTracker(unittest.TestCase):
    def test_requires_three_matching_observations(self):
        tracker = RouteStabilityTracker()
        match = match_route_text("barakahu")
        self.assertIsNotNone(match)

        self.assertIsNone(tracker.observe(7, match))
        self.assertIsNone(tracker.observe(7, match))
        stable = tracker.observe(7, match)

        self.assertIsNotNone(stable)
        self.assertEqual(stable.route_line, "Green Line")
        self.assertEqual(stable.direction_id, "toward_barakahu")

    def test_two_observations_are_not_stable(self):
        tracker = RouteStabilityTracker()
        match = match_route_text("N 5")
        self.assertIsNone(tracker.observe(3, match))
        self.assertIsNone(tracker.observe(3, match))
        self.assertIsNone(tracker.get_stable(3))

    def test_clear_inactive_drops_missing_tracks(self):
        tracker = RouteStabilityTracker()
        match = match_route_text("PIMS Hospital")
        tracker.observe(1, match)
        tracker.observe(1, match)
        tracker.observe(1, match)
        self.assertIsNotNone(tracker.get_stable(1))

        tracker.clear_inactive(active_track_ids={99})
        self.assertIsNone(tracker.get_stable(1))


if __name__ == "__main__":
    unittest.main()
