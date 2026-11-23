import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from controller import SlimeController


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
            controller = SlimeController(data_dir=directory)
            with patch(
                "orchestration.run_orchestration",
                return_value=fake_report,
            ) as run:
                result = controller.execute("PLAN")

        self.assertTrue(result["accepted"])
        self.assertTrue(result["plan_available"])
        self.assertEqual(result["recommended_group"], ["A", "B"])
        self.assertFalse(result["evidence_gate_passed"])
        self.assertFalse(result["touch_events_sent"])
        self.assertFalse(result["live_execution_allowed"])
        run.assert_called_once()

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
