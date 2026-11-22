import unittest
from snapshot_sync import synchronise_audit


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
        report = synchronise_audit(board, observations)
        self.assertTrue(report["synchronised"])

    def test_mismatched_snapshot(self):
        board, observations = self.valid_data()
        observations["board_snapshot_id"] = "capture-002"
        report = synchronise_audit(board, observations)
        self.assertFalse(report["synchronised"])

    def test_mismatched_session(self):
        board, observations = self.valid_data()
        observations["capture_session_id"] = "session-002"
        report = synchronise_audit(board, observations)
        self.assertFalse(report["synchronised"])

    def test_missing_timestamp(self):
        board, observations = self.valid_data()
        board.pop("captured_at")
        report = synchronise_audit(board, observations)
        self.assertFalse(report["synchronised"])

    def test_confirmation_required(self):
        board, observations = self.valid_data()
        observations["same_board_state_confirmed"] = False
        report = synchronise_audit(board, observations)
        self.assertFalse(report["synchronised"])

    def test_game_taps_always_disabled(self):
        board, observations = self.valid_data()
        report = synchronise_audit(board, observations)
        self.assertFalse(report["game_taps_enabled"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
