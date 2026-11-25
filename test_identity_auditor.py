import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from identity_auditor import audit_identity, build_report


SNAPSHOT = "sha256:" + "a" * 64
SESSION = "session-123"
CAPTURED_AT = "2026-11-25T08:00:00+00:00"
POSITIONS = [
    "bottom_1", "bottom_2", "right_1", "right_2",
    "top_1", "top_2", "left_1", "left_2",
]


def valid_bundle():
    board = {
        "source_sha256": "a" * 64,
        "snapshot_id": SNAPSHOT,
        "board_snapshot_id": SNAPSHOT,
        "capture_session_id": SESSION,
        "captured_at": CAPTURED_AT,
        "timestamp_identified": True,
    }
    visual = {
        "board_snapshot_id": SNAPSHOT,
        "capture_session_id": SESSION,
        "captured_at": CAPTURED_AT,
        "timestamp_identified": True,
        "same_board_state_confirmed": True,
        "observations": [
            {"position_id": position, "colour": "white", "ammo": 10}
            for position in POSITIONS
        ],
    }
    identity = {
        "board_snapshot_id": SNAPSHOT,
        "capture_session_id": SESSION,
        "captured_at": CAPTURED_AT,
        "timestamp_identified": True,
        "verified_by_user": True,
        "current_frame_id": "identity-frame-1",
        "observations": [
            {
                "frame_id": "identity-frame-1",
                "position_id": position,
                "shooter_id": f"shooter-{index}",
                "verified": True,
            }
            for index, position in enumerate(POSITIONS)
        ],
    }
    calibration = {
        "shooters": [{"id": position, "center": [index, index]}
                     for index, position in enumerate(POSITIONS)]
    }
    detection = {
        "visible_shooters": [{"id": f"shooter-{index}"}
                             for index in range(len(POSITIONS))]
    }
    return board, visual, identity, calibration, detection


class IdentityAuditorTests(unittest.TestCase):
    def test_complete_user_confirmed_capture_mapping_passes(self):
        report = audit_identity(*valid_bundle())
        self.assertTrue(report["identity_verified"])
        self.assertEqual(report["positions_checked"], 8)
        self.assertEqual(len(report["known_shooters"]), 8)
        self.assertEqual(report["errors"], [])
        self.assertIs(report["timestamps_known"], True)
        self.assertFalse(report["gameplay_verified"])
        self.assertFalse(report["game_taps_enabled"])

    def test_user_confirmation_is_required(self):
        board, visual, identity, calibration, detection = valid_bundle()
        identity["verified_by_user"] = False
        report = audit_identity(board, visual, identity, calibration, detection)
        self.assertFalse(report["identity_verified"])
        self.assertTrue(any("not explicitly user-confirmed" in x for x in report["blockers"]))

    def test_every_identity_record_must_be_confirmed(self):
        board, visual, identity, calibration, detection = valid_bundle()
        identity["observations"][0]["verified"] = False
        report = audit_identity(board, visual, identity, calibration, detection)
        self.assertFalse(report["identity_verified"])
        self.assertTrue(any("not individually user-confirmed" in x for x in report["blockers"]))

    def test_timestamps_known_requires_all_three_capture_timestamps(self):
        for source in ("board", "visual", "identity"):
            with self.subTest(source=source):
                board, visual, identity, calibration, detection = valid_bundle()
                if source == "board":
                    board["timestamp_identified"] = False
                elif source == "visual":
                    visual["timestamp_identified"] = False
                else:
                    identity["timestamp_identified"] = False
                report = audit_identity(
                    board, visual, identity, calibration, detection
                )
                self.assertFalse(report["timestamps_known"])
                self.assertFalse(report["identity_verified"])

    def test_board_snapshot_mismatch_blocks(self):
        board, visual, identity, calibration, detection = valid_bundle()
        identity["board_snapshot_id"] = "sha256:" + "b" * 64
        report = audit_identity(board, visual, identity, calibration, detection)
        self.assertFalse(report["identity_verified"])
        self.assertTrue(any("current board snapshot" in x for x in report["blockers"]))

    def test_stale_visual_timestamp_blocks(self):
        board, visual, identity, calibration, detection = valid_bundle()
        visual["captured_at"] = "2026-11-25T07:55:00+00:00"
        report = audit_identity(board, visual, identity, calibration, detection)
        self.assertFalse(report["identity_verified"])
        self.assertTrue(any("more than 120 seconds" in x for x in report["blockers"]))

    def test_duplicate_position_blocks(self):
        board, visual, identity, calibration, detection = valid_bundle()
        identity["observations"][1]["position_id"] = POSITIONS[0]
        report = audit_identity(board, visual, identity, calibration, detection)
        self.assertFalse(report["identity_verified"])
        self.assertTrue(any("Duplicate position" in x for x in report["blockers"]))

    def test_duplicate_shooter_assignment_blocks(self):
        board, visual, identity, calibration, detection = valid_bundle()
        identity["observations"][1]["shooter_id"] = "shooter-0"
        report = audit_identity(board, visual, identity, calibration, detection)
        self.assertFalse(report["identity_verified"])
        self.assertTrue(any("duplicate shooter" in x for x in report["blockers"]))

    def test_multiple_frames_can_track_same_shooter_across_positions(self):
        board, visual, identity, calibration, detection = valid_bundle()
        identity["observations"].append({
            "frame_id": "historical-frame",
            "position_id": "bottom_1",
            "shooter_id": "shooter-0",
            "verified": True,
        })
        report = audit_identity(board, visual, identity, calibration, detection)
        self.assertTrue(report["identity_verified"])
        self.assertEqual(len(report["identity_frame_ids"]), 2)
        self.assertEqual(
            report["current_position_by_shooter"]["shooter-0"],
            "bottom_1",
        )
        self.assertIn("bottom_1", report["shooter_positions"]["shooter-0"])

    def test_unknown_shooter_blocks(self):
        board, visual, identity, calibration, detection = valid_bundle()
        identity["observations"][0]["shooter_id"] = "not-detected"
        report = audit_identity(board, visual, identity, calibration, detection)
        self.assertFalse(report["identity_verified"])
        self.assertTrue(any("unknown shooter" in x for x in report["blockers"]))

    def test_visual_positions_must_cover_calibration(self):
        board, visual, identity, calibration, detection = valid_bundle()
        visual["observations"].pop()
        report = audit_identity(board, visual, identity, calibration, detection)
        self.assertFalse(report["identity_verified"])
        self.assertTrue(any("do not exactly match calibrated positions" in x for x in report["blockers"]))

    def test_non_object_board_is_handled_without_crashing(self):
        report = audit_identity([], {}, {}, {}, {})
        self.assertFalse(report["identity_verified"])
        self.assertTrue(report["errors"])

    def test_build_report_hashes_exact_source_bytes(self):
        board, visual, identity, calibration, detection = valid_bundle()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payloads = {
                "board.json": board,
                "visual.json": visual,
                "identity.json": identity,
                "calibration.json": calibration,
                "detection.json": detection,
            }
            paths = {}
            raw = {}
            for name, payload in payloads.items():
                paths[name] = root / name
                raw[name] = json.dumps(payload, separators=(",", ":")).encode()
                paths[name].write_bytes(raw[name])

            report = build_report(
                board_path=paths["board.json"],
                visual_path=paths["visual.json"],
                identity_path=paths["identity.json"],
                calibration_path=paths["calibration.json"],
                detection_path=paths["detection.json"],
            )
            self.assertTrue(report["identity_verified"])
            self.assertEqual(
                report["source_file_sha256"]["board_observation_json"],
                hashlib.sha256(raw["board.json"]).hexdigest(),
            )
            self.assertEqual(
                report["source_file_sha256"]["shooter_identity_observations_json"],
                hashlib.sha256(raw["identity.json"]).hexdigest(),
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
