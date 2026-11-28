import io
import unittest
from unittest.mock import patch, MagicMock

import command_dispatcher


class CommandDispatcherTests(unittest.TestCase):
    def setUp(self):
        self.stdout = io.StringIO()
        self.patcher = patch("sys.stdout", self.stdout)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()

    def test_tap_is_blocked_when_disabled(self):
        result = command_dispatcher.send_command("TAP")
        self.assertFalse(result)
        self.assertIn("BLOCKED: Game tapping is not enabled.", self.stdout.getvalue())

    def test_unknown_command_is_rejected(self):
        result = command_dispatcher.send_command("UNKNOWN")
        self.assertFalse(result)
        self.assertIn("REJECTED: Unknown command:", self.stdout.getvalue())
        self.assertIn("UNKNOWN", self.stdout.getvalue())

    def test_whitespace_and_case_are_normalized(self):
        with patch("command_dispatcher.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="")
            result = command_dispatcher.send_command("  ping  ")
            self.assertTrue(result)
            mock_run.assert_called_once()
            args = mock_run.call_args[0][0]
            self.assertEqual(args[-1], "PING")

    def test_allowed_command_success_path(self):
        with patch("command_dispatcher.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="")
            result = command_dispatcher.send_command("STATUS")
            self.assertTrue(result)
            self.assertIn("Command sent: STATUS", self.stdout.getvalue())

    def test_subprocess_failure_is_reported(self):
        with patch("command_dispatcher.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stderr="boom")
            result = command_dispatcher.send_command("PAUSE")
            self.assertFalse(result)
            self.assertIn("Communication error: boom", self.stdout.getvalue())

    def test_system_status_reports_taps_disabled(self):
        command_dispatcher.system_status()
        output = self.stdout.getvalue()
        self.assertIn("Game tapping: DISABLED", output)
        self.assertIn("Solver: under development", output)
        self.assertNotIn("ENABLED", output.split("Game tapping:")[-1].splitlines()[0])

    def test_tap_enabled_flag_remains_false(self):
        self.assertFalse(command_dispatcher.TAP_ENABLED)


if __name__ == "__main__":
    unittest.main()
