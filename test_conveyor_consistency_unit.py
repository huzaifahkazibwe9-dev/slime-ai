import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from conveyor_consistency_auditor import (
    build_consistency_report,
    main,
    read_json_snapshot,
)


ORDER = ["bottom", "right", "top", "left"]
SERIES = {
    "white": [
        ("bottom_1", 40),
        ("right_2", 30),
        ("top_2", 25),
        ("left_1", 25),
    ],
    "blue_cyan": [
        ("bottom_2", 40),
        ("right_1", 27),
        ("top_1", 18),
        ("left_2", 0),
    ],
}


def make_inputs(sequence_confirmed=False):
    original = []
    snapshots = []
    for index, side in enumerate(ORDER):
        white_position, white_ammo = SERIES["white"][index]
        blue_position, blue_ammo = SERIES["blue_cyan"][index]
        white = {
            "position_id": white_position,
            "colour": "white",
            "ammo": white_ammo,
        }
        blue = {
            "position_id": blue_position,
            "colour": "blue",
            "ammo": blue_ammo,
        }
        original.extend([white, blue])
        snapshots.append({
            "sequence": index + 1,
            "side": side,
            "white_candidate": white,
            "blue_cyan_candidate": blue,
        })
    visual = {"observations": original}
    timeline = {
        "sequence": ORDER,
        "sequence_confirmed_by_user": sequence_confirmed,
        "captured_at": "2026-11-25T10:00:00+00:00",
        "timestamps_known": True,
        "identity_verified": False,
        "snapshots": snapshots,
    }
    return timeline, visual


class ConveyorConsistencyUnitTests(unittest.TestCase):
    def test_consistency_report_is_position_only_and_source_bound(self):
        timeline, visual = make_inputs(sequence_confirmed=False)
        report = build_consistency_report(
            timeline,
            visual,
            {
                "conveyor_timeline_json": "a" * 64,
                "conveyor_visual_observations_json": "b" * 64,
            },
        )

        self.assertEqual(report["overall_status"], "CONSISTENT_POSITION_DATA")
        self.assertFalse(report["sequence_confirmed_by_user"])
        self.assertTrue(report["timestamps_known"])
        self.assertFalse(report["identity_verified"])
        self.assertFalse(report["gameplay_verified"])
        self.assertFalse(report["game_taps_enabled"])
        self.assertEqual(
            report["position_series"]["white"]["ammunition"],
            [40, 30, 25, 25],
        )
        self.assertEqual(
            report["position_series"]["blue_cyan"]["ammunition"],
            [40, 27, 18, 0],
        )
        for series in report["position_series"].values():
            self.assertNotIn("candidate_shooter", series)
            self.assertEqual(
                series["identity_status"],
                "UNRESOLVED_POSITION_SERIES_ONLY",
            )
        self.assertEqual(
            report["source_file_sha256"]["conveyor_timeline_json"],
            "a" * 64,
        )

    def test_increasing_ammunition_is_reported_as_inconsistency(self):
        timeline, visual = make_inputs()
        timeline["snapshots"][2]["white_candidate"]["ammo"] = 45
        visual["observations"][4]["ammo"] = 45
        report = build_consistency_report(timeline, visual)
        self.assertEqual(report["overall_status"], "INCONSISTENCIES_FOUND")
        self.assertTrue(any(
            "ammunition increased" in error for error in report["errors"]
        ))

    def test_duplicate_or_missing_original_positions_are_rejected(self):
        timeline, visual = make_inputs()
        visual["observations"].pop()
        with self.assertRaisesRegex(ValueError, "Duplicate|missing|Original"):
            # The duplicate position case must not pass silently.
            visual["observations"].append(dict(visual["observations"][0]))
            build_consistency_report(timeline, visual)

    def test_unreadable_utf8_source_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            path.write_bytes(bytes((255, 254)))
            with self.assertRaisesRegex(ValueError, "UTF-8"):
                read_json_snapshot(path)

    def test_main_writes_blocked_report_when_input_is_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "report.json"
            report = main(
                root / "missing_timeline.json",
                root / "missing_observations.json",
                output,
            )
            self.assertEqual(report["overall_status"], "EVIDENCE_UNAVAILABLE")
            self.assertFalse(report["identity_verified"])
            self.assertFalse(report["game_taps_enabled"])
            self.assertEqual(json.loads(output.read_text()), report)


if __name__ == "__main__":
    unittest.main(verbosity=2)
