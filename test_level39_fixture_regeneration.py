"""Reproducibility checks for the ported Level 39 JSON fixtures.

These tests verify only that derived JSON reports can be rebuilt from the
repository's structured source records. They do not authenticate screenshots
or establish physical shooter identity or game mechanics.
"""

import json
import unittest
from pathlib import Path

from conveyor_consistency_auditor import audit
from conveyor_timeline import build_timeline

DATA = Path("data")


def _load(name):
    return json.loads((DATA / name).read_text())


class Level39FixtureRegenerationTests(unittest.TestCase):
    def test_timeline_is_reproducible_from_source_observations(self):
        visual = _load("conveyor_visual_observations.json")
        saved = _load("conveyor_timeline.json")
        self.assertEqual(saved, build_timeline(visual))

    def test_consistency_report_is_reproducible(self):
        visual = _load("conveyor_visual_observations.json")
        timeline = _load("conveyor_timeline.json")
        saved = _load("conveyor_consistency_report.json")
        self.assertEqual(saved, audit(timeline, visual))

    def test_fixture_safety_flags_remain_disabled(self):
        visual = _load("conveyor_visual_observations.json")
        timeline = _load("conveyor_timeline.json")
        report = _load("conveyor_consistency_report.json")
        mapping = _load("color_matches.json")

        self.assertFalse(visual["identity_verified"])
        self.assertFalse(visual["gameplay_verified"])
        self.assertFalse(timeline["sequence_confirmed_by_user"])
        self.assertFalse(timeline["identity_verified"])
        self.assertFalse(timeline["gameplay_taps_enabled"])
        self.assertFalse(report["identity_verified"])
        self.assertFalse(report["gameplay_taps_enabled"])
        self.assertFalse(mapping["verified_by_gameplay"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
