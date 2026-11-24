import json
import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from controller import SlimeController


def write_capture_pair(directory, captured_at=None, shooter_hash=None):
    captured_at = captured_at or datetime.now(timezone.utc).isoformat()
    source_hash = "a" * 64
    board = {
        "source_sha256": source_hash,
        "snapshot_id": "sha256:" + source_hash,
        "board_snapshot_id": "sha256:" + source_hash,
        "capture_session_id": "session-abc",
        "captured_at": captured_at,
    }
    shooter = {
        "capture_provenance": {
            "verified": True,
            "source_sha256": shooter_hash or source_hash,
            "capture_session_id": "session-abc",
            "captured_at": captured_at,
        }
    }
    root = Path(directory)
    (root / "board_observation_latest.json").write_text(json.dumps(board))
    (root / "shooter_detection.json").write_text(json.dumps(shooter))


class ControllerTests(unittest.TestCase):
    def test_initial_status_is_plan_only_and_not_ready(self):
        with tempfile.TemporaryDirectory() as directory:
            controller = SlimeController(data_dir=directory)
            status = controller.status()

        self.assertEqual(status["mode"], "PLAN_ONLY")
        self.assertFalse(status["gameplay_ready"])
        self.assertFalse(status["tap_enabled"])
        self.assertFalse(status["touch_injection"])

    def test_tap_is_always_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            result = SlimeController(data_dir=directory).execute("TAP")

        self.assertFalse(result["accepted"])
        self.assertFalse(result["touch_events_sent"])
        self.assertFalse(result["live_execution_allowed"])

    def test_paused_controller_does_not_run_planner(self):
        with tempfile.TemporaryDirectory() as directory:
            controller = SlimeController(data_dir=directory)
            controller.execute("PAUSE")
            with patch("orchestration.run_orchestration") as run:
                result = controller.execute("PLAN")

        self.assertFalse(result["accepted"])
        run.assert_not_called()

    def test_plan_delegates_to_orchestration_without_live_actions(self):
        fake_report = {
            "planner": {"recommended_group": ["A", "B"]},
            "decision": "BLOCKED_NO_VERIFIED_PLAN",
            "evidence": {"evidence_gate_passed": False},
            "game_taps_enabled": False,
            "live_execution_allowed": False,
            "actions_performed": False,
        }
        with tempfile.TemporaryDirectory() as directory:
            write_capture_pair(directory)
            controller = SlimeController(data_dir=directory)
            with patch(
                "orchestration.run_orchestration",
                return_value=fake_report,
            ) as run:
                result = controller.execute("PLAN")

        self.assertTrue(result["accepted"])
        self.assertFalse(result["plan_available"])
        self.assertIsNone(result["recommended_group"])
        self.assertFalse(result["evidence_gate_passed"])
        self.assertFalse(result["touch_events_sent"])
        self.assertFalse(result["live_execution_allowed"])
        run.assert_called_once()

    def test_plan_blocks_when_capture_files_are_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            controller = SlimeController(data_dir=directory)
            with patch("orchestration.run_orchestration") as run:
                result = controller.execute("PLAN")
        self.assertFalse(result["accepted"])
        self.assertIn("fresh screenshot capture is required", result["reason"])
        run.assert_not_called()

    def test_plan_blocks_stale_capture_before_orchestration(self):
        stale = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
        with tempfile.TemporaryDirectory() as directory:
            write_capture_pair(directory, captured_at=stale)
            controller = SlimeController(data_dir=directory)
            with patch("orchestration.run_orchestration") as run:
                result = controller.execute("PLAN")
        self.assertFalse(result["accepted"])
        self.assertIn("stale", result["reason"])
        run.assert_not_called()

    def test_plan_blocks_board_shooter_hash_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            write_capture_pair(directory, shooter_hash="b" * 64)
            controller = SlimeController(data_dir=directory)
            with patch("orchestration.run_orchestration") as run:
                result = controller.execute("PLAN")
        self.assertFalse(result["accepted"])
        self.assertIn("screenshot hash", result["reason"])
        run.assert_not_called()

    def test_controller_hides_candidate_when_evidence_gate_fails(self):
        fake_report = {
            "planner": {"recommended_group": ["A"]},
            "decision": "BLOCKED_NO_VERIFIED_PLAN",
            "evidence": {"evidence_gate_passed": False},
        }
        with tempfile.TemporaryDirectory() as directory:
            write_capture_pair(directory)
            write_capture_pair(directory)
            controller = SlimeController(data_dir=directory)
            with patch(
                "orchestration.run_orchestration",
                return_value=fake_report,
            ):
                result = controller.execute("PLAN")
        self.assertFalse(result["plan_available"])
        self.assertIsNone(result["recommended_group"])
        self.assertFalse(result["evidence_gate_passed"])

    def test_no_candidate_is_reported_as_no_plan(self):
        fake_report = {
            "planner": {"recommended_group": None},
            "decision": "BLOCKED_NO_VERIFIED_PLAN",
            "evidence": {"evidence_gate_passed": False},
        }
        with tempfile.TemporaryDirectory() as directory:
            controller = SlimeController(data_dir=directory)
            with patch(
                "orchestration.run_orchestration",
                return_value=fake_report,
            ):
                result = controller.execute("PLAN")

        self.assertTrue(result["accepted"])
        self.assertFalse(result["plan_available"])
        self.assertIsNone(result["recommended_group"])

    def test_status_never_promotes_external_readiness_flags(self):
        with tempfile.TemporaryDirectory() as directory:
            report_path = Path(directory) / "orchestration_latest.json"
            report_path.write_text(json.dumps({
                "gameplay_ready": True,
                "game_taps_enabled": True,
                "decision": "VERIFIED_PLAN_AVAILABLE_BUT_LIVE_ACTIONS_DISABLED",
                "evidence": {"evidence_gate_passed": True},
                "planner": {"recommended_group": ["A"]},
            }))
            status = SlimeController(data_dir=directory).status()

        self.assertFalse(status["gameplay_ready"])
        self.assertFalse(status["tap_enabled"])
        self.assertFalse(status["touch_injection"])
        self.assertTrue(status["plan_available"])

    def test_unknown_command_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            result = SlimeController(data_dir=directory).execute("DELETE")

        self.assertFalse(result["accepted"])
        self.assertFalse(result["touch_events_sent"])


if __name__ == "__main__":
    unittest.main()
