import unittest

from conveyor_timeline import build_timeline_report


POSITIONS = {
    "bottom_1": ("white", 38),
    "right_2": ("white", 33),
    "top_2": ("white", 26),
    "left_1": ("white", 26),
    "bottom_2": ("blue", 40),
    "right_1": ("blue", 27),
    "top_1": ("blue", 18),
    "left_2": ("blue", 0),
}


def visual_fixture():
    return {
        "board_snapshot_id": "sha256:" + "a" * 64,
        "capture_session_id": "session-001",
        "captured_at": "2026-11-25T10:00:00+00:00",
        "timestamp_identified": True,
        "same_board_state_confirmed": True,
        "sequence_confirmed_by_user": False,
        "observations": [
            {
                "position_id": position,
                "colour": colour,
                "ammo": ammo,
            }
            for position, (colour, ammo) in POSITIONS.items()
        ],
    }


class ConveyorTimelineUnitTests(unittest.TestCase):
    def test_timeline_preserves_position_series_without_shooter_assignment(self):
        report = build_timeline_report(visual_fixture(), "b" * 64)

        self.assertEqual(report["sequence"], ["bottom", "right", "top", "left"])
        self.assertEqual(
            report["candidate_tracks"]["white"]["ammo"],
            [38, 33, 26, 26],
        )
        self.assertEqual(
            report["candidate_tracks"]["blue_cyan"]["ammo"],
            [40, 27, 18, 0],
        )
        self.assertIsNone(report["candidate_tracks"]["white"]["candidate_shooter"])
        self.assertIsNone(report["candidate_tracks"]["blue_cyan"]["candidate_shooter"])
        self.assertFalse(report["identity_verified"])
        self.assertFalse(report["gameplay_verified"])
        self.assertFalse(report["game_taps_enabled"])

    def test_timeline_does_not_claim_user_sequence_confirmation(self):
        visual = visual_fixture()
        visual["sequence_confirmed_by_user"] = False
        report = build_timeline_report(visual)
        self.assertFalse(report["sequence_confirmed_by_user"])

        visual["sequence_confirmed_by_user"] = True
        report = build_timeline_report(visual)
        self.assertTrue(report["sequence_confirmed_by_user"])

    def test_timeline_derives_timezone_aware_timestamp_status(self):
        visual = visual_fixture()
        report = build_timeline_report(visual)
        self.assertTrue(report["timestamps_known"])

        visual["captured_at"] = "2026-11-25T10:00:00"
        report = build_timeline_report(visual)
        self.assertFalse(report["timestamps_known"])

        visual["timestamp_identified"] = False
        visual["captured_at"] = "2026-11-25T10:00:00+00:00"
        report = build_timeline_report(visual)
        self.assertFalse(report["timestamps_known"])

    def test_timeline_rejects_missing_or_duplicate_positions(self):
        visual = visual_fixture()
        visual["observations"].pop()
        with self.assertRaisesRegex(ValueError, "layout"):
            build_timeline_report(visual)

        visual = visual_fixture()
        visual["observations"].append(dict(visual["observations"][0]))
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            build_timeline_report(visual)

    def test_timeline_rejects_boolean_ammunition(self):
        visual = visual_fixture()
        visual["observations"][0]["ammo"] = True
        with self.assertRaisesRegex(ValueError, "ammunition"):
            build_timeline_report(visual)


if __name__ == "__main__":
    unittest.main(verbosity=2)
