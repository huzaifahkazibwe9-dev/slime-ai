"""Synthetic offline coverage for conveyor timeline and consistency.

These fixtures are invented structural examples. They are not Level 39
captures, not screenshots, and not a substitute for the private evidence
files that keep the public evidence tests skipped.
"""

import unittest

from conveyor_consistency_auditor import audit
from conveyor_timeline import build_timeline

SYNTHETIC_CAPTURE_ID = "synthetic-offline-not-a-game-capture"


def _observation(position_id, ammo, colour):
    return {
        "capture_id": SYNTHETIC_CAPTURE_ID,
        "evidence_class": "synthetic",
        "position_id": position_id,
        "ammo": ammo,
        "colour": colour,
    }


def _synthetic_visual():
    # Deliberately different from any recorded Level 39 ammunition series.
    rows = [
        ("bottom_1", 9, "white"),
        ("right_2", 7, "white"),
        ("top_2", 4, "white"),
        ("left_1", 4, "white"),
        ("bottom_2", 8, "blue"),
        ("right_1", 5, "blue"),
        ("top_1", 5, "blue"),
        ("left_2", 0, "blue"),
    ]
    return {
        "capture_id": SYNTHETIC_CAPTURE_ID,
        "evidence_class": "synthetic",
        "identity_verified": False,
        "observations": [
            _observation(position_id, ammo, colour)
            for position_id, ammo, colour in rows
        ],
    }


class SyntheticConveyorOfflineTests(unittest.TestCase):
    def test_builder_preserves_eight_synthetic_observations(self):
        visual = _synthetic_visual()
        report = build_timeline(visual)

        self.assertEqual(report["sequence"], ["bottom", "right", "top", "left"])
        self.assertEqual(len(report["snapshots"]), 4)
        original = {
            item["position_id"]: item for item in visual["observations"]
        }
        for step in report["snapshots"]:
            for key in ("white_candidate", "blue_cyan_candidate"):
                item = step[key]
                self.assertEqual(item, original[item["position_id"]])
                self.assertEqual(item["evidence_class"], "synthetic")

    def test_builder_does_not_invent_user_confirmation(self):
        report = build_timeline(_synthetic_visual())
        self.assertFalse(report["sequence_confirmed_by_user"])
        self.assertFalse(report["timestamps_known"])
        self.assertFalse(report["identity_verified"])
        self.assertFalse(report["gameplay_taps_enabled"])

        confirmed = build_timeline(
            _synthetic_visual(),
            sequence_confirmed_by_user=True,
        )
        self.assertTrue(confirmed["sequence_confirmed_by_user"])
        self.assertFalse(confirmed["identity_verified"])
        self.assertFalse(confirmed["gameplay_taps_enabled"])

    def test_missing_position_is_rejected(self):
        visual = _synthetic_visual()
        visual["observations"] = [
            item for item in visual["observations"]
            if item["position_id"] != "left_2"
        ]
        with self.assertRaises(ValueError):
            build_timeline(visual)

    def test_synthetic_consistency_uses_distinct_ammunition(self):
        visual = _synthetic_visual()
        timeline = build_timeline(visual)
        report = audit(timeline, visual)

        self.assertEqual(report["overall_status"], "CONSISTENT_CANDIDATE_DATA")
        self.assertEqual(
            report["candidate_tracks"]["white"]["ammunition"],
            [9, 7, 4, 4],
        )
        self.assertEqual(
            report["candidate_tracks"]["blue_cyan"]["ammunition"],
            [8, 5, 5, 0],
        )
        self.assertEqual(
            report["candidate_tracks"]["white"]["positions"],
            ["bottom_1", "right_2", "top_2", "left_1"],
        )
        self.assertEqual(
            report["candidate_tracks"]["blue_cyan"]["positions"],
            ["bottom_2", "right_1", "top_1", "left_2"],
        )
        self.assertEqual(
            report["candidate_tracks"]["blue_cyan"]["depletion_status"],
            "zero_ammunition_observed",
        )
        self.assertFalse(report["identity_verified"])
        self.assertFalse(report["gameplay_taps_enabled"])
        self.assertTrue(
            all(item["evidence_class"] == "synthetic" for item in visual["observations"])
        )

    def test_ammunition_increase_is_an_inconsistency(self):
        visual = _synthetic_visual()
        for item in visual["observations"]:
            if item["position_id"] == "right_2":
                item["ammo"] = 12
        timeline = build_timeline(visual)
        report = audit(timeline, visual)

        self.assertEqual(report["overall_status"], "INCONSISTENCIES_FOUND")
        self.assertFalse(report["checks"]["no_ammunition_increases"])
        self.assertFalse(report["gameplay_taps_enabled"])
        self.assertFalse(
            report["candidate_tracks"]["white"]["non_increasing"]
        )

    def test_mutated_snapshot_is_not_preserved(self):
        visual = _synthetic_visual()
        timeline = build_timeline(visual)
        timeline["snapshots"][0]["white_candidate"] = dict(
            timeline["snapshots"][0]["white_candidate"],
            ammo=1,
        )
        report = audit(timeline, visual)
        self.assertEqual(report["overall_status"], "INCONSISTENCIES_FOUND")
        self.assertFalse(
            report["candidate_tracks"]["white"]["original_observations_preserved"]
        )
        self.assertFalse(report["identity_verified"])


    def test_duplicate_position_is_rejected(self):
        visual = _synthetic_visual()
        duplicate = dict(visual["observations"][0], ammo=3)
        visual["observations"].append(duplicate)
        with self.assertRaisesRegex(ValueError, "Duplicate observation"):
            build_timeline(visual)

    def test_boolean_ammunition_is_rejected(self):
        visual = _synthetic_visual()
        visual["observations"][0]["ammo"] = True
        with self.assertRaisesRegex(ValueError, "non-negative integer ammo"):
            build_timeline(visual)

    def test_confirmation_requires_a_boolean(self):
        with self.assertRaisesRegex(ValueError, "must be a Boolean"):
            build_timeline(
                _synthetic_visual(),
                sequence_confirmed_by_user="yes",
            )

    def test_auditor_reports_duplicate_source_positions(self):
        visual = _synthetic_visual()
        timeline = build_timeline(visual)
        visual["observations"].append(dict(visual["observations"][0]))
        report = audit(timeline, visual)
        self.assertEqual(report["overall_status"], "INCONSISTENCIES_FOUND")
        self.assertTrue(any(
            "Duplicate original observation position_id" in error
            for error in report["errors"]
        ))


    def test_auditor_rejects_colour_mismatch_for_position_track(self):
        visual = _synthetic_visual()
        visual["observations"][1]["colour"] = "blue"
        timeline = build_timeline(visual)
        report = audit(timeline, visual)
        self.assertEqual(report["overall_status"], "INCONSISTENCIES_FOUND")
        self.assertTrue(any(
            "unexpected colour" in error for error in report["errors"]
        ))

    def test_auditor_rejects_cached_ammunition_summary_mismatch(self):
        visual = _synthetic_visual()
        timeline = build_timeline(visual)
        timeline["candidate_tracks"]["white"]["ammo"] = [9, 7, 4, 3]
        report = audit(timeline, visual)
        self.assertEqual(report["overall_status"], "INCONSISTENCIES_FOUND")
        self.assertTrue(any(
            "cached ammunition summary differs" in error
            for error in report["errors"]
        ))

    def test_auditor_rejects_non_boolean_sequence_confirmation(self):
        visual = _synthetic_visual()
        timeline = build_timeline(visual)
        timeline["sequence_confirmed_by_user"] = "true"
        report = audit(timeline, visual)
        self.assertEqual(report["overall_status"], "INCONSISTENCIES_FOUND")
        self.assertFalse(report["sequence_confirmed_by_user"])
        self.assertTrue(any(
            "sequence_confirmed_by_user must be a Boolean" in error
            for error in report["errors"]
        ))

    def test_auditor_rejects_unexpected_source_positions(self):
        visual = _synthetic_visual()
        visual["observations"].append(
            _observation("extra_position", 2, "white")
        )
        timeline = build_timeline(visual)
        report = audit(timeline, visual)
        self.assertEqual(report["overall_status"], "INCONSISTENCIES_FOUND")
        self.assertTrue(any(
            "Unexpected source observation positions" in error
            for error in report["errors"]
        ))


if __name__ == "__main__":
    unittest.main(verbosity=2)
