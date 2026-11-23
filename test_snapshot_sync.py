import unittest
from datetime import datetime, timedelta, timezone
from snapshot_sync import synchronise_audit, synchronise_bundle


class SnapshotSyncTests(unittest.TestCase):
    def valid_data(self):
        now = datetime.now(timezone.utc)
        board = {
            "snapshot_id": "capture-001",
            "capture_session_id": "session-001",
            "timestamp_identified": True,
            "captured_at": now.isoformat(),
        }
        observations = {
            "board_snapshot_id": "capture-001",
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
            "snapshot_id": "capture-001",
            "capture_session_id": "session-001",
            "captured_at": captured_at,
            "timestamp_identified": True,
        }
        artifacts = [
            {
                "board_snapshot_id": "capture-001",
                "capture_session_id": "session-001",
                "captured_at": captured_at,
                "timestamp_identified": True,
            }
            for _ in range(4)
        ]
        return board, *artifacts

    def test_bundle_requires_all_artifacts_from_same_capture(self):
        board, conveyor, identity, candidates, planning = self.bundle()
        result = synchronise_bundle(board, conveyor, identity, candidates, planning)
        self.assertTrue(result["synchronised"])
        self.assertTrue(result["planning_allowed_by_sync"])
        self.assertFalse(result["game_taps_enabled"])

    def test_bundle_rejects_mixed_screenshot_snapshot(self):
        board, conveyor, identity, candidates, planning = self.bundle()
        identity["board_snapshot_id"] = "different-screenshot"
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

    def test_bundle_rejects_missing_artifact(self):
        board, conveyor, identity, _, planning = self.bundle()
        result = synchronise_bundle(board, conveyor, identity, None, planning)
        self.assertFalse(result["synchronised"])
        self.assertFalse(result["checks"]["candidates_artifact_present"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
