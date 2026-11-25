import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from conveyor_identity_matcher import (
    validate_visual_observations,
    validate_visual_provenance,
    validate_observation_provenance,
    validate_identity_audit,
    read_snapshot,
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
    def test_read_snapshot_hashes_exact_json_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            raw = b'{ "value": 9 }'
            path = Path(directory) / "sample.json"
            path.write_bytes(raw)
            with patch("conveyor_identity_matcher.DATA", Path(directory)):
                value, digest = read_snapshot("sample.json")
        self.assertEqual(value, {"value": 9})
        self.assertEqual(digest, hashlib.sha256(raw).hexdigest())

    def identity_fixture(self):
        snapshot_id = "sha256:" + "a" * 64
        captured_at = "2026-11-25T08:00:00+00:00"
        board = {
            "snapshot_id": snapshot_id,
            "source_sha256": "a" * 64,
            "capture_session_id": "session-001",
            "captured_at": captured_at,
        }
        visual = {
            "board_snapshot_id": snapshot_id,
            "capture_session_id": "session-001",
            "captured_at": captured_at,
        }
        identity = {
            "identity_verified": True,
            "errors": [],
            "blockers": [],
            "board_snapshot_id": snapshot_id,
            "capture_session_id": "session-001",
            "captured_at": captured_at,
            "timestamp_identified": True,
            "verified_by_user": True,
            "positions_checked": 2,
            "known_shooters": ["A", "B"],
            "shooter_positions": {"A": ["bottom_1"], "B": ["bottom_2"]},
            "current_position_by_shooter": {"A": "bottom_1", "B": "bottom_2"},
            "source_file_sha256": {
                "board_observation_json": "a" * 64,
                "conveyor_visual_observations_json": "b" * 64,
                "shooter_identity_observations_json": "c" * 64,
                "conveyor_calibration_json": "d" * 64,
                "shooter_detection_json": "e" * 64,
            },
        }
        expected = dict(identity["source_file_sha256"])
        return identity, board, visual, {"bottom_1", "bottom_2"}, expected

    def test_matching_human_identity_audit_is_accepted(self):
        identity, board, visual, positions, expected = self.identity_fixture()
        errors, mapping = validate_identity_audit(
            identity, board, visual, positions, expected
        )
        self.assertEqual(errors, [])
        self.assertEqual(mapping["A"], ["bottom_1"])
        self.assertEqual(mapping["B"], ["bottom_2"])

    def test_stale_identity_source_fingerprint_is_rejected(self):
        identity, board, visual, positions, expected = self.identity_fixture()
        expected["shooter_detection_json"] = "f" * 64
        errors, _ = validate_identity_audit(
            identity, board, visual, positions, expected
        )
        self.assertTrue(any("source fingerprints" in item for item in errors))

    def test_unverified_identity_report_is_rejected(self):
        identity, board, visual, positions, expected = self.identity_fixture()
        identity["identity_verified"] = False
        errors, _ = validate_identity_audit(
            identity, board, visual, positions, expected
        )
        self.assertTrue(any("not verified" in item for item in errors))

    def test_incomplete_current_position_map_is_rejected(self):
        identity, board, visual, positions, expected = self.identity_fixture()
        identity["current_position_by_shooter"].pop("B")
        errors, _ = validate_identity_audit(
            identity, board, visual, positions, expected
        )
        self.assertTrue(any("current frame" in item for item in errors))

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
