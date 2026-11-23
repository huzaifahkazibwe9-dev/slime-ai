import unittest

from conveyor_identity_matcher import (
    validate_visual_observations,
    validate_visual_provenance,
    validate_observation_provenance,
)


EXPECTED = [
    "bottom_1", "bottom_2", "right_1", "right_2",
    "top_1", "top_2", "left_1", "left_2",
]


def observations():
    return [
        {"position_id": position, "colour": "white", "ammo": 10}
        for position in EXPECTED
    ]


class ConveyorIdentityMatcherTests(unittest.TestCase):
    def test_complete_unique_frame_is_valid(self):
        self.assertEqual(
            validate_visual_observations(observations(), EXPECTED), []
        )


    def test_explicit_capture_provenance_is_valid(self):
        self.assertEqual(validate_visual_provenance({
            "board_snapshot_id": "sha256:" + "a" * 64,
            "capture_session_id": "session-001",
            "captured_at": "2026-11-23T10:00:00+03:00",
            "timestamp_identified": True,
        }), [])


    def test_observation_capture_mismatch_is_rejected(self):
        visual = {
            "board_snapshot_id": "sha256:" + "a" * 64,
            "capture_session_id": "session-001",
            "captured_at": "2026-11-23T10:00:00+03:00",
            "timestamp_identified": True,
        }
        data = observations()
        data[0]["board_snapshot_id"] = "sha256:" + "b" * 64
        errors = validate_observation_provenance(data, visual)
        self.assertTrue(any("board_snapshot_id conflicts" in item for item in errors))

    def test_observation_without_duplicate_metadata_inherits_parent(self):
        visual = {
            "board_snapshot_id": "sha256:" + "a" * 64,
            "capture_session_id": "session-001",
            "captured_at": "2026-11-23T10:00:00+03:00",
            "timestamp_identified": True,
        }
        self.assertEqual(validate_observation_provenance(observations(), visual), [])

    def test_malformed_snapshot_id_is_rejected(self):
        errors = validate_visual_provenance({
            "board_snapshot_id": "board-1",
            "capture_session_id": "session-001",
            "captured_at": "2026-11-23T10:00:00+03:00",
            "timestamp_identified": True,
        })
        self.assertTrue(any("board_snapshot_id" in item for item in errors))

    def test_malformed_capture_session_id_is_rejected(self):
        errors = validate_visual_provenance({
            "board_snapshot_id": "sha256:" + "a" * 64,
            "capture_session_id": "bad session id",
            "captured_at": "2026-11-23T10:00:00+03:00",
            "timestamp_identified": True,
        })
        self.assertTrue(any("capture_session_id" in item for item in errors))

    def test_missing_snapshot_link_is_rejected(self):
        errors = validate_visual_provenance({
            "capture_session_id": "session-001",
            "captured_at": "2026-11-23T10:00:00+03:00",
            "timestamp_identified": True,
        })
        self.assertTrue(any("board_snapshot_id" in item for item in errors))

    def test_naive_capture_timestamp_is_rejected(self):
        errors = validate_visual_provenance({
            "board_snapshot_id": "sha256:" + "a" * 64,
            "capture_session_id": "session-001",
            "captured_at": "2026-11-23T10:00:00",
            "timestamp_identified": True,
        })
        self.assertTrue(any("UTC offset" in item for item in errors))

    def test_unidentified_capture_timestamp_is_rejected(self):
        errors = validate_visual_provenance({
            "board_snapshot_id": "sha256:" + "a" * 64,
            "capture_session_id": "session-001",
            "captured_at": "2026-11-23T10:00:00+03:00",
            "timestamp_identified": False,
        })
        self.assertTrue(any("not explicitly identified" in item for item in errors))

    def test_duplicate_position_rejected(self):
        data = observations()
        data[-1] = dict(data[0])
        errors = validate_visual_observations(data, EXPECTED)
        self.assertTrue(any("Duplicate position" in x for x in errors))

    def test_missing_position_rejected(self):
        errors = validate_visual_observations(
            observations()[:-1], EXPECTED
        )
        self.assertTrue(any("Missing positions" in x for x in errors))

    def test_unexpected_position_rejected(self):
        data = observations()
        data[-1]["position_id"] = "left_9"
        errors = validate_visual_observations(data, EXPECTED)
        self.assertTrue(any("Unexpected position" in x for x in errors))

    def test_negative_ammunition_rejected(self):
        data = observations()
        data[0]["ammo"] = -1
        errors = validate_visual_observations(data, EXPECTED)
        self.assertTrue(any("invalid ammunition" in x for x in errors))

    def test_boolean_ammunition_rejected(self):
        data = observations()
        data[0]["ammo"] = True
        errors = validate_visual_observations(data, EXPECTED)
        self.assertTrue(any("invalid ammunition" in x for x in errors))

    def test_unknown_colour_rejected(self):
        data = observations()
        data[0]["colour"] = "orange"
        errors = validate_visual_observations(data, EXPECTED)
        self.assertTrue(any("invalid colour" in x for x in errors))

    def test_non_list_rejected(self):
        self.assertTrue(
            validate_visual_observations(None, EXPECTED)
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
