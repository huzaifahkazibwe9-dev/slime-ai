import unittest
from snapshot_sync import synchronise_audit, synchronise_bundle


class SnapshotSyncTests(unittest.TestCase):
    def valid_data(self):
        board = {
            "snapshot_id": "capture-001",
            "capture_session_id": "session-001",
            "timestamp_identified": True,
            "captured_at": "2026-11-21T10:00:00+03:00",
        }
        observations = {
            "board_snapshot_id": "capture-001",
            "capture_session_id": "session-001",
            "timestamp_identified": True,
            "captured_at": "2026-11-21T10:00:00+03:00",
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

    def test_game_taps_always_disabled(self):
        board, observations = self.valid_data()
        self.assertFalse(synchronise_audit(board, observations)["game_taps_enabled"])

    def bundle(self):
        board = {"snapshot_id": "capture-001", "capture_session_id": "session-001"}
        artifacts = [
            {"board_snapshot_id": "capture-001", "capture_session_id": "session-001"}
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

    def test_bundle_rejects_missing_artifact(self):
        board, conveyor, identity, _, planning = self.bundle()
        result = synchronise_bundle(board, conveyor, identity, None, planning)
        self.assertFalse(result["synchronised"])
        self.assertFalse(result["checks"]["candidates_artifact_present"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
