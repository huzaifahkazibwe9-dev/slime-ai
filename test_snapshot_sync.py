import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from snapshot_sync import (
    main as run_snapshot_sync,
    read_input_snapshots, synchronise_audit, synchronise_bundle,
)


class SnapshotSyncTests(unittest.TestCase):
    def test_input_snapshot_hashes_exact_parsed_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            board_path = Path(directory) / "vision_level39.json"
            observations_path = Path(directory) / "conveyor_visual_observations.json"
            board_bytes = b'{ "grid_size": [35, 35], "bounds": [1, 2, 3, 4] }'
            observation_bytes = b'{ "observations": [], "captured_at": "2026-11-23T10:00:00+00:00" }'
            board_path.write_bytes(board_bytes)
            observations_path.write_bytes(observation_bytes)

            board, observations, hashes = read_input_snapshots(
                board_path, observations_path
            )

            self.assertEqual(board["grid_size"], [35, 35])
            self.assertEqual(observations["observations"], [])
            self.assertEqual(hashes, {
                "vision_level39_json": hashlib.sha256(board_bytes).hexdigest(),
                "conveyor_observations_json": hashlib.sha256(
                    observation_bytes
                ).hexdigest(),
            })

    def test_input_snapshot_hashes_screenshot_observation_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            board_path = Path(directory) / "board_observation_latest.json"
            observations_path = Path(directory) / "conveyor_visual_observations.json"
            board_bytes = b'{"raw_rgb": [[[1, 2, 3]]], "snapshot_id": "sha256:' + b"1" * 64 + b'"}'
            observation_bytes = b'{"observations": []}'
            board_path.write_bytes(board_bytes)
            observations_path.write_bytes(observation_bytes)

            board, observations, hashes = read_input_snapshots(
                board_path, observations_path
            )

            self.assertIn("raw_rgb", board)
            self.assertEqual(observations["observations"], [])
            self.assertEqual(hashes, {
                "board_observation_json": hashlib.sha256(board_bytes).hexdigest(),
                "conveyor_observations_json": hashlib.sha256(
                    observation_bytes
                ).hexdigest(),
            })

    def test_main_writes_blocked_report_for_unreadable_utf8_input(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            board_path = root / "board.json"
            observations_path = root / "observations.json"
            output_path = root / "snapshot_sync_report.json"
            board_path.write_bytes(bytes((255, 254)))
            observations_path.write_text(json.dumps({"observations": []}))

            report = run_snapshot_sync(
                board_path, observations_path, output_path
            )

            self.assertFalse(report["synchronised"])
            self.assertFalse(report["planning_allowed_by_sync"])
            self.assertIn("input_error", report)
            self.assertFalse(report["game_taps_enabled"])
            self.assertTrue(output_path.is_file())
            self.assertEqual(json.loads(output_path.read_text()), report)

    def test_main_writes_blocked_report_for_non_object_json_input(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            board_path = root / "board.json"
            observations_path = root / "observations.json"
            output_path = root / "snapshot_sync_report.json"
            board_path.write_text("[]")
            observations_path.write_text("{}")

            report = run_snapshot_sync(
                board_path, observations_path, output_path
            )

            self.assertFalse(report["synchronised"])
            self.assertFalse(report["planning_allowed_by_sync"])
            self.assertIn("JSON object", report["input_error"])
            self.assertFalse(report["game_taps_enabled"])

    def test_input_snapshot_reader_rejects_non_object_payload(self):
        with tempfile.TemporaryDirectory() as directory:
            board_path = Path(directory) / "board.json"
            observations_path = Path(directory) / "observations.json"
            board_path.write_text("[]")
            observations_path.write_text("{}")
            with self.assertRaisesRegex(ValueError, "JSON object"):
                read_input_snapshots(board_path, observations_path)

    def valid_data(self):
        now = datetime.now(timezone.utc)
        board = {
            "snapshot_id": "sha256:" + "a" * 64,
            "capture_session_id": "session-001",
            "timestamp_identified": True,
            "captured_at": now.isoformat(),
        }
        observations = {
            "board_snapshot_id": "sha256:" + "a" * 64,
            "capture_session_id": "session-001",
            "timestamp_identified": True,
            "captured_at": (now - timedelta(seconds=30)).isoformat(),
            "same_board_state_confirmed": True,
        }
        return board, observations

    def test_matching_metadata(self):
        board, observations = self.valid_data()
        self.assertTrue(synchronise_audit(board, observations)["synchronised"])

    def test_mismatched_snapshot(self):
        board, observations = self.valid_data()
        observations["board_snapshot_id"] = "capture-002"
        self.assertFalse(synchronise_audit(board, observations)["synchronised"])

    def test_mismatched_session(self):
        board, observations = self.valid_data()
        observations["capture_session_id"] = "session-002"
        self.assertFalse(synchronise_audit(board, observations)["synchronised"])

    def test_missing_timestamp(self):
        board, observations = self.valid_data()
        board.pop("captured_at")
        self.assertFalse(synchronise_audit(board, observations)["synchronised"])

    def test_confirmation_required(self):
        board, observations = self.valid_data()
        observations["same_board_state_confirmed"] = False
        self.assertFalse(synchronise_audit(board, observations)["synchronised"])

    def test_capture_freshness_accepts_recent_aligned_timestamps(self):
        from snapshot_sync import validate_capture_freshness
        now = datetime(2026, 11, 23, 10, 0, tzinfo=timezone.utc)
        result = validate_capture_freshness(
            "2026-11-23T09:59:00+00:00",
            "2026-11-23T09:59:30+00:00",
            now=now,
        )
        self.assertTrue(result["fresh"])

    def test_capture_freshness_rejects_stale_screenshot(self):
        from snapshot_sync import validate_capture_freshness
        now = datetime(2026, 11, 23, 10, 0, tzinfo=timezone.utc)
        result = validate_capture_freshness(
            "2026-11-23T09:00:00+00:00",
            "2026-11-23T09:00:30+00:00",
            now=now,
        )
        self.assertFalse(result["fresh"])
        self.assertFalse(result["checks"]["board_capture_fresh"])

    def test_capture_freshness_rejects_naive_timestamp(self):
        from snapshot_sync import validate_capture_freshness
        now = datetime(2026, 11, 23, 10, 0, tzinfo=timezone.utc)
        result = validate_capture_freshness(
            "2026-11-23T09:59:00",
            "2026-11-23T09:59:30+00:00",
            now=now,
        )
        self.assertFalse(result["fresh"])

    def test_capture_freshness_rejects_excessive_timestamp_skew(self):
        from snapshot_sync import validate_capture_freshness
        now = datetime(2026, 11, 23, 10, 0, tzinfo=timezone.utc)
        result = validate_capture_freshness(
            "2026-11-23T09:59:00+00:00",
            "2026-11-23T09:55:00+00:00",
            now=now,
        )
        self.assertFalse(result["fresh"])
        self.assertFalse(result["checks"]["capture_timestamps_within_skew_limit"])

    def test_game_taps_always_disabled(self):
        board, observations = self.valid_data()
        self.assertFalse(synchronise_audit(board, observations)["game_taps_enabled"])

    def bundle(self):
        captured_at = "2026-11-23T10:00:00+00:00"
        board = {
            "snapshot_id": "sha256:" + "a" * 64,
            "capture_session_id": "session-001",
            "captured_at": captured_at,
            "timestamp_identified": True,
        }
        artifacts = [
            {
                "board_snapshot_id": "sha256:" + "a" * 64,
                "capture_session_id": "session-001",
                "captured_at": captured_at,
                "timestamp_identified": True,
            }
            for _ in range(4)
        ]
        artifacts[0]["observations"] = [
            {"position_id": f"position-{index}"}
            for index in range(8)
        ]
        positions = {
            "white": ("bottom_1", "right_2", "top_2", "left_1"),
            "blue_cyan": ("bottom_2", "right_1", "top_1", "left_2"),
        }
        artifacts[2]["tracks"] = {
            name: {
                "board_snapshot_id": "sha256:" + "a" * 64,
                "capture_session_id": "session-001",
                "captured_at": captured_at,
                "timestamp_identified": True,
                "observations": [
                    {
                        "position_id": position,
                        "board_snapshot_id": "sha256:" + "a" * 64,
                        "capture_session_id": "session-001",
                        "captured_at": captured_at,
                        "timestamp_identified": True,
                    }
                    for position in track_positions
                ],
            }
            for name, track_positions in positions.items()
        }
        return board, *artifacts

    def test_bundle_requires_all_artifacts_from_same_capture(self):
        board, conveyor, identity, candidates, planning = self.bundle()
        result = synchronise_bundle(board, conveyor, identity, candidates, planning)
        self.assertTrue(result["synchronised"])
        self.assertTrue(result["planning_allowed_by_sync"])
        self.assertFalse(result["game_taps_enabled"])

    def test_bundle_rejects_mixed_screenshot_snapshot(self):
        board, conveyor, identity, candidates, planning = self.bundle()
        identity["board_snapshot_id"] = "sha256:" + "b" * 64
        result = synchronise_bundle(board, conveyor, identity, candidates, planning)
        self.assertFalse(result["synchronised"])
        self.assertFalse(result["planning_allowed_by_sync"])
        self.assertFalse(result["checks"]["identity_snapshot_matches_board"])

    def test_bundle_rejects_mixed_capture_session(self):
        board, conveyor, identity, candidates, planning = self.bundle()
        candidates["capture_session_id"] = "other-session"
        result = synchronise_bundle(board, conveyor, identity, candidates, planning)
        self.assertFalse(result["synchronised"])
        self.assertFalse(result["checks"]["candidates_session_matches_board"])

    def test_bundle_rejects_missing_provenance(self):
        board, conveyor, identity, candidates, planning = self.bundle()
        del conveyor["board_snapshot_id"]
        result = synchronise_bundle(board, conveyor, identity, candidates, planning)
        self.assertFalse(result["synchronised"])
        self.assertFalse(result["checks"]["conveyor_snapshot_id_present"])

    def test_bundle_rejects_planning_from_different_capture(self):
        board, conveyor, identity, candidates, planning = self.bundle()
        planning["capture_session_id"] = "stale-session"
        result = synchronise_bundle(
            board, conveyor, identity, candidates, planning
        )
        self.assertFalse(result["synchronised"])
        self.assertFalse(result["checks"]["planning_session_matches_board"])

    def test_bundle_rejects_artifact_from_different_capture_time(self):
        board, conveyor, identity, candidates, planning = self.bundle()
        candidates["captured_at"] = "2026-11-23T10:03:00+00:00"
        result = synchronise_bundle(
            board, conveyor, identity, candidates, planning
        )
        self.assertFalse(result["synchronised"])
        self.assertFalse(
            result["checks"]["candidates_timestamp_matches_board"]
        )
        candidates["captured_at"] = "2026-11-23T10:01:00+00:00"
        within_limit = synchronise_bundle(
            board, conveyor, identity, candidates, planning
        )
        self.assertTrue(within_limit["synchronised"])

    def test_bundle_rejects_unidentified_artifact_timestamp(self):
        board, conveyor, identity, candidates, planning = self.bundle()
        identity["timestamp_identified"] = False
        result = synchronise_bundle(
            board, conveyor, identity, candidates, planning
        )
        self.assertFalse(result["synchronised"])
        self.assertFalse(
            result["checks"]["identity_timestamp_identified"]
        )

    def test_bundle_rejects_nested_conveyor_observation_from_other_capture(self):
        board, conveyor, identity, candidates, planning = self.bundle()
        conveyor["observations"][0]["board_snapshot_id"] = "other-capture"
        result = synchronise_bundle(
            board, conveyor, identity, candidates, planning
        )
        self.assertFalse(result["synchronised"])
        self.assertFalse(
            result["checks"]["conveyor_nested_capture_metadata_consistent"]
        )

    def test_bundle_rejects_nested_candidate_observation_from_other_session(self):
        board, conveyor, identity, candidates, planning = self.bundle()
        candidates["tracks"]["white"]["observations"][0][
            "capture_session_id"
        ] = "other-session"
        result = synchronise_bundle(
            board, conveyor, identity, candidates, planning
        )
        self.assertFalse(result["synchronised"])
        self.assertFalse(
            result["checks"]["candidates_nested_capture_metadata_consistent"]
        )

    def test_bundle_rejects_nested_candidate_timestamp_skew(self):
        board, conveyor, identity, candidates, planning = self.bundle()
        candidates["tracks"]["blue_cyan"]["observations"][0][
            "captured_at"
        ] = "2026-11-23T10:03:00+00:00"
        result = synchronise_bundle(
            board, conveyor, identity, candidates, planning
        )
        self.assertFalse(result["synchronised"])
        self.assertFalse(
            result["checks"]["candidates_nested_capture_metadata_consistent"]
        )

    def test_bundle_rejects_missing_nested_conveyor_observations(self):
        board, conveyor, identity, candidates, planning = self.bundle()
        conveyor.pop("observations")
        result = synchronise_bundle(
            board, conveyor, identity, candidates, planning
        )
        self.assertFalse(result["synchronised"])
        self.assertFalse(
            result["checks"]["conveyor_nested_capture_metadata_consistent"]
        )

    def test_bundle_rejects_missing_candidate_tracks(self):
        board, conveyor, identity, candidates, planning = self.bundle()
        candidates.pop("tracks")
        result = synchronise_bundle(
            board, conveyor, identity, candidates, planning
        )
        self.assertFalse(result["synchronised"])
        self.assertFalse(
            result["checks"]["candidates_nested_capture_metadata_consistent"]
        )

    def test_bundle_rejects_missing_artifact(self):
        board, conveyor, identity, _, planning = self.bundle()
        result = synchronise_bundle(board, conveyor, identity, None, planning)
        self.assertFalse(result["synchronised"])
        self.assertFalse(result["checks"]["candidates_artifact_present"])


    def test_bundle_rejects_board_source_digest_mismatch(self):
        board, conveyor, identity, candidates, planning = self.bundle()
        board["source_sha256"] = "b" * 64
        result = synchronise_bundle(
            board, conveyor, identity, candidates, planning
        )
        self.assertFalse(result["synchronised"])
        self.assertFalse(
            result["checks"]["board_source_digest_matches_snapshot"]
        )

    def test_bundle_accepts_matching_board_source_digest(self):
        board, conveyor, identity, candidates, planning = self.bundle()
        board["source_sha256"] = "a" * 64
        result = synchronise_bundle(
            board, conveyor, identity, candidates, planning
        )
        self.assertTrue(result["synchronised"])
        self.assertTrue(
            result["checks"]["board_source_digest_matches_snapshot"]
        )

    def test_bundle_rejects_artifact_source_digest_mismatch(self):
        board, conveyor, identity, candidates, planning = self.bundle()
        identity["source_sha256"] = "b" * 64
        result = synchronise_bundle(
            board, conveyor, identity, candidates, planning
        )
        self.assertFalse(result["synchronised"])
        self.assertFalse(
            result["checks"]["identity_source_digest_matches_snapshot"]
        )

    def test_bundle_rejects_malformed_artifact_source_digest(self):
        board, conveyor, identity, candidates, planning = self.bundle()
        planning["source_sha256"] = "not-a-sha256"
        result = synchronise_bundle(
            board, conveyor, identity, candidates, planning
        )
        self.assertFalse(result["synchronised"])
        self.assertFalse(
            result["checks"]["planning_source_digest_matches_snapshot"]
        )

    def test_capture_freshness_rejects_invalid_thresholds(self):
        from snapshot_sync import validate_capture_freshness
        now = datetime(2026, 11, 23, 10, 0, tzinfo=timezone.utc)
        for value in (-1, True, float("nan"), float("inf"), "300"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    validate_capture_freshness(
                        "2026-11-23T09:59:00+00:00",
                        "2026-11-23T09:59:30+00:00",
                        now=now,
                        max_age_seconds=value,
                    )

    def test_capture_freshness_accepts_arbitrarily_large_finite_integer_limits(self):
        from snapshot_sync import validate_capture_freshness
        now = datetime(2026, 11, 23, 10, 0, tzinfo=timezone.utc)
        huge = 10 ** 10000
        result = validate_capture_freshness(
            "2026-11-23T09:59:00+00:00",
            "2026-11-23T09:59:30+00:00",
            now=now,
            max_age_seconds=huge,
            max_skew_seconds=huge,
        )
        self.assertTrue(result["fresh"])
        self.assertEqual(result["max_age_seconds"], huge)
        self.assertEqual(result["max_skew_seconds"], huge)

    def test_capture_freshness_rejects_invalid_now(self):
        from snapshot_sync import validate_capture_freshness
        with self.assertRaisesRegex(ValueError, "timezone-aware datetime"):
            validate_capture_freshness("x", "y", now="not-a-datetime")

    def test_sync_audit_rejects_non_object_metadata(self):
        for board, observations in (([], {}), ({}, []), (None, {})):
            with self.subTest(board=board, observations=observations):
                with self.assertRaisesRegex(ValueError, "JSON objects"):
                    synchronise_audit(board, observations)


if __name__ == "__main__":
    unittest.main(verbosity=2)
