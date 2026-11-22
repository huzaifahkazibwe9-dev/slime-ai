import unittest

from unittest.mock import patch
import command_dispatcher as dispatcher


class AndroidBridgeSafetyTests(unittest.TestCase):

    def test_action_is_correct(self):
        self.assertEqual(
            dispatcher.ACTION,
            "com.slimeai.TEST"
        )

    def test_only_four_commands_are_allowed(self):
        self.assertEqual(
            dispatcher.ALLOWED_COMMANDS,
            {"PING", "STATUS", "PAUSE", "RESUME"}
        )

    def test_tapping_remains_disabled(self):
        self.assertFalse(dispatcher.TAP_ENABLED)

    def test_tap_is_rejected_without_broadcast(self):
        with patch.object(dispatcher.subprocess, "run") as mocked:
            result = dispatcher.send_command("TAP")

        self.assertFalse(result)
        mocked.assert_not_called()

    def test_unknown_command_is_rejected(self):
        with patch.object(dispatcher.subprocess, "run") as mocked:
            result = dispatcher.send_command("UNKNOWN")

        self.assertFalse(result)
        mocked.assert_not_called()

    def test_command_arguments_are_correct(self):
        expected = [
            "am", "broadcast",
            "-a", "com.slimeai.TEST",
            "--es", "command", "PING"
        ]

        with patch.object(
            dispatcher.subprocess,
            "run",
            return_value=type(
                "Result",
                (),
                {"returncode": 0, "stdout": "", "stderr": ""}
            )()
        ) as mocked:
            result = dispatcher.send_command("PING")

        self.assertTrue(result)
        self.assertEqual(mocked.call_args.args[0], expected)


if __name__ == "__main__":
    unittest.main(verbosity=2)
