import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from identity_auditor import audit_identity
import conveyor_identity_matcher
import conveyor_identity_matcher

from conveyor_identity_matcher import (
    validate_visual_observations,
    validate_visual_provenance,
    validate_observation_provenance,
    validate_identity_audit,
    validate_calibration_positions,
    validate_required_position_layout,
    derive_candidate_track,
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
    def test_read_snapshot_rejects_unreadable_utf8_payload(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.json"
            path.write_bytes(bytes((255, 254)))
            with patch.object(conveyor_identity_matcher, "DATA", Path(directory)):
                with self.assertRaisesRegex(ValueError, "unreadable JSON"):
                    read_snapshot("invalid.json")

    def test_main_writes_blocked_report_for_missing_or_invalid_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(conveyor_identity_matcher, "DATA", root):
                report = conveyor_identity_matcher.main()

            self.assertIsInstance(report, dict)
            self.assertFalse(report["identity_verified"])
            self.assertFalse(report["candidate_provenance_verified"])
            self.assertFalse(report["game_taps_enabled"])
            self.assertTrue(any(
                "conveyor_calibration.json" in error
                for error in report["validation_errors"]
            ))
            saved = json.loads(
                (root / "conveyor_identity_candidates.json").read_text()
            )
            self.assertEqual(saved, report)

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
            "timestamps_known": True,
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

    def test_identity_audit_with_unknown_timestamps_is_rejected(self):
        identity, board, visual, positions, expected = self.identity_fixture()
        identity["timestamps_known"] = False
        errors, _ = validate_identity_audit(
            identity, board, visual, positions, expected
        )
        self.assertTrue(any("timestamps" in item for item in errors))

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

    def test_calibration_position_geometry_requires_valid_segment_and_center(self):
        valid = {
            "bottom_1": {"segment": "bottom", "center": [10, 20]},
            "top_1": {"segment": "top", "center": [30.5, 40]},
        }
        self.assertEqual(validate_calibration_positions(valid), [])
        invalid = {
            "bottom_1": {"segment": "diagonal", "center": [10, 20]},
            "top_1": {"segment": "top", "center": [30, float("inf")]},
        }
        errors = validate_calibration_positions(invalid)
        self.assertEqual(len(errors), 2)
        self.assertTrue(any("segment" in error for error in errors))
        self.assertTrue(any("center" in error for error in errors))

    def test_calibration_record_list_rejects_duplicate_ids(self):
        records = [
            {"id": "bottom_1", "segment": "bottom", "center": [10, 20]},
            {"id": "bottom_1", "segment": "bottom", "center": [11, 21]},
        ]
        errors = validate_calibration_positions(records)
        self.assertTrue(any("Duplicate calibrated position ID" in error for error in errors))

    def test_calibration_record_list_rejects_malformed_records(self):
        records = [
            None,
            {"id": "", "segment": "bottom", "center": [10, 20]},
            {"id": "top_1", "segment": "top", "center": [10, True]},
        ]
        errors = validate_calibration_positions(records)
        self.assertEqual(len(errors), 3)

    def test_required_conveyor_layout_requires_all_eight_named_slots(self):
        valid = {
            f"{side}_{slot}": {
                "segment": side, "center": [slot * 10, slot * 20]
            }
            for side in ("bottom", "right", "top", "left")
            for slot in (1, 2)
        }
        self.assertEqual(validate_required_position_layout(valid), [])
        del valid["left_2"]
        errors = validate_required_position_layout(valid)
        self.assertTrue(any("left_2" in error for error in errors))

    def test_required_conveyor_layout_rejects_segment_id_mismatch(self):
        positions = {
            f"{side}_{slot}": {
                "segment": "top" if side == "bottom" and slot == 1 else side,
                "center": [10, 20],
            }
            for side in ("bottom", "right", "top", "left")
            for slot in (1, 2)
        }
        errors = validate_required_position_layout(positions)
        self.assertTrue(any("segment does not match" in error for error in errors))

    def test_candidate_track_uses_unique_historical_intersection(self):
        positions = ["bottom_1", "right_2", "top_2", "left_1"]
        shooter_positions = {
            "shooter-A": positions,
            "shooter-B": ["bottom_2", "right_1", "top_1", "left_2"],
        }
        calibrated = {
            position: {"segment": position.split("_")[0], "center": [10, 20]}
            for position in positions
        }
        visual = {
            "board_snapshot_id": "sha256:" + "a" * 64,
            "capture_session_id": "session-001",
            "captured_at": "2026-11-25T08:00:00+00:00",
            "timestamp_identified": True,
        }
        observations = {
            position: {"position_id": position, "colour": "white", "ammo": ammo}
            for position, ammo in zip(positions, (40, 30, 20, 10))
        }
        track = derive_candidate_track(
            "white",
            {"positions": positions, "allowed_panel_colours": {"white"}},
            shooter_positions,
            {"shooter-A": "bottom_1", "shooter-B": "bottom_2"},
            {"shooter-A": {"color": {"name": "white"}}},
            calibrated,
            observations,
            visual,
        )
        self.assertEqual(track["candidate_shooter"], "shooter-A")
        self.assertEqual(track["current_position_id"], "bottom_1")
        self.assertTrue(track["candidate_supported"])
        self.assertTrue(track["ammo_non_increasing"])
        self.assertTrue(track["panel_colour_match"])
        self.assertTrue(track["observed_colour_consistent"])

    def test_candidate_track_rejects_ambiguous_historical_intersection(self):
        positions = ["bottom_1", "right_2", "top_2", "left_1"]
        shooter_positions = {
            "shooter-A": positions,
            "shooter-B": positions,
        }
        calibrated = {
            position: {"segment": position.split("_")[0], "center": [10, 20]}
            for position in positions
        }
        visual = {"board_snapshot_id": "sha256:" + "a" * 64}
        observations = {
            position: {"position_id": position, "colour": "white", "ammo": 10}
            for position in positions
        }
        track = derive_candidate_track(
            "white",
            {"positions": positions, "allowed_panel_colours": {"white"}},
            shooter_positions,
            {"shooter-A": "bottom_1", "shooter-B": "bottom_2"},
            {"shooter-A": {"color": {"name": "white"}}},
            calibrated,
            observations,
            visual,
        )
        self.assertIsNone(track["candidate_shooter"])
        self.assertFalse(track["candidate_supported"])

    def test_candidate_track_requires_current_position_in_observed_track(self):
        positions = ["bottom_1", "right_2", "top_2", "left_1"]
        calibrated = {
            position: {"segment": position.split("_")[0], "center": [10, 20]}
            for position in positions
        }
        visual = {"board_snapshot_id": "sha256:" + "a" * 64}
        observations = {
            position: {"position_id": position, "colour": "white", "ammo": 10}
            for position in positions
        }
        track = derive_candidate_track(
            "white",
            {"positions": positions, "allowed_panel_colours": {"white"}},
            {"shooter-A": positions},
            {"shooter-A": "bottom_2"},
            {"shooter-A": {"color": {"name": "white"}}},
            calibrated,
            observations,
            visual,
        )
        self.assertEqual(track["candidate_shooter"], "shooter-A")
        self.assertFalse(track["candidate_supported"])

    def test_main_fails_closed_on_empty_calibration_without_key_error(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payloads = {
                "board_observation_latest.json": {},
                "conveyor_visual_observations.json": {"observations": []},
                "shooter_detection.json": {"visible_shooters": []},
                "identity_audit_report.json": {},
                "conveyor_calibration.json": {"shooters": []},
            }
            for name, payload in payloads.items():
                (root / name).write_text(json.dumps(payload))
            with patch.object(conveyor_identity_matcher, "DATA", root):
                report = conveyor_identity_matcher.main()
            self.assertFalse(report["candidate_provenance_verified"])
            self.assertEqual(report["tracks"], {})
            self.assertTrue(any(
                "Calibration shooter list" in error
                or "Missing required conveyor positions" in error
                for error in report["validation_errors"]
            ))

    def test_main_builds_candidate_bound_to_confirmed_identity_and_snapshot(self):
        positions = [
            "bottom_1", "bottom_2", "right_1", "right_2",
            "top_1", "top_2", "left_1", "left_2",
        ]
        captured_at = "2026-11-25T09:00:00+00:00"
        source_digest = "a" * 64
        snapshot_id = "sha256:" + source_digest
        session_id = "session-001"
        board = {
            "source_sha256": source_digest,
            "snapshot_id": snapshot_id,
            "board_snapshot_id": snapshot_id,
            "capture_session_id": session_id,
            "captured_at": captured_at,
            "timestamp_identified": True,
        }
        visual_colours = {
            "bottom_1": ("white", 40),
            "bottom_2": ("cyan", 40),
            "right_1": ("blue", 30),
            "right_2": ("white", 30),
            "top_1": ("cyan", 20),
            "top_2": ("white", 20),
            "left_1": ("white", 10),
            "left_2": ("blue", 10),
        }
        visual = {
            "board_snapshot_id": snapshot_id,
            "capture_session_id": session_id,
            "captured_at": captured_at,
            "timestamp_identified": True,
            "same_board_state_confirmed": True,
            "identity_verified": False,
            "gameplay_verified": False,
            "observations": [
                {
                    "position_id": position,
                    "colour": visual_colours[position][0],
                    "ammo": visual_colours[position][1],
                }
                for position in positions
            ],
        }
        calibration = {
            "verified_by_user": True,
            "shooters": [
                {
                    "id": position,
                    "segment": position.split("_")[0],
                    "center": [index * 10 + 5, index * 10 + 7],
                }
                for index, position in enumerate(positions)
            ],
        }
        shooter_ids = [f"shooter-{index}" for index in range(4)]
        detection = {
            "visible_shooters": [
                {
                    "id": shooter_ids[index],
                    "color": {"name": "white" if index == 0 else "cyan"},
                    "ammo": 40,
                    "bonded_ids": (
                        [shooter_ids[1]] if index == 0
                        else [shooter_ids[0]] if index == 1 else []
                    ),
                }
                for index in range(4)
            ]
        }
        current_frame = [
            {
                "frame_id": "current",
                "position_id": position,
                "shooter_id": shooter_ids[index],
                "verified": True,
            }
            for index, position in enumerate(positions[:4])
        ]
        historical = []
        white_track = [
            ("right_2", "shooter-0"),
            ("top_2", "shooter-0"),
            ("left_1", "shooter-0"),
        ]
        blue_track = [
            ("right_1", "shooter-1"),
            ("top_1", "shooter-1"),
            ("left_2", "shooter-1"),
        ]
        for index, (position, shooter_id) in enumerate(white_track + blue_track):
            historical.append({
                "frame_id": f"history-{index}",
                "position_id": position,
                "shooter_id": shooter_id,
                "verified": True,
            })
        identity_observations = {
            "board_snapshot_id": snapshot_id,
            "capture_session_id": session_id,
            "captured_at": captured_at,
            "timestamp_identified": True,
            "verified_by_user": True,
            "current_frame_id": "current",
            "observations": current_frame + historical,
        }

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payloads = {
                "board_observation_latest.json": board,
                "conveyor_visual_observations.json": visual,
                "shooter_detection.json": detection,
                "conveyor_calibration.json": calibration,
                "shooter_identity_observations.json": identity_observations,
            }
            source_bytes = {}
            for name, payload in payloads.items():
                raw = json.dumps(payload, separators=(",", ":")).encode()
                (root / name).write_bytes(raw)
                source_bytes[name] = raw

            identity_report = audit_identity(
                board, visual, identity_observations, calibration, detection
            )
            identity_report["source_file_sha256"] = {
                "board_observation_json": hashlib.sha256(
                    source_bytes["board_observation_latest.json"]
                ).hexdigest(),
                "conveyor_visual_observations_json": hashlib.sha256(
                    source_bytes["conveyor_visual_observations.json"]
                ).hexdigest(),
                "shooter_identity_observations_json": hashlib.sha256(
                    source_bytes["shooter_identity_observations.json"]
                ).hexdigest(),
                "conveyor_calibration_json": hashlib.sha256(
                    source_bytes["conveyor_calibration.json"]
                ).hexdigest(),
                "shooter_detection_json": hashlib.sha256(
                    source_bytes["shooter_detection.json"]
                ).hexdigest(),
            }
            (root / "identity_audit_report.json").write_text(
                json.dumps(identity_report)
            )

            with patch.object(conveyor_identity_matcher, "DATA", root):
                report = conveyor_identity_matcher.main()

            self.assertTrue(identity_report["identity_verified"])
            self.assertEqual(report["current_snapshot_id"], snapshot_id)
            self.assertTrue(report["checks"]["current_snapshot_identified"])
            self.assertTrue(report["checks"]["identity_previously_verified"])
            self.assertTrue(report["candidate_provenance_verified"])
            self.assertEqual(
                [report["tracks"][name]["candidate_shooter"]
                 for name in ("white", "blue_cyan")],
                ["shooter-0", "shooter-1"],
            )
            self.assertTrue(
                all(track["candidate_supported"]
                    for track in report["tracks"].values())
            )
            self.assertFalse(report["gameplay_verified"])
            self.assertFalse(report["game_taps_enabled"])

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
