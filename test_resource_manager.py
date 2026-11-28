import unittest

from resource_manager import Mode, ResourceManager


class ResourceManagerTests(unittest.TestCase):
    def setUp(self):
        self.manager = ResourceManager()

    def test_starts_in_idle_with_taps_disabled(self):
        self.assertEqual(self.manager.mode, Mode.IDLE)
        self.assertFalse(self.manager.game_taps_enabled)
        status = self.manager.status()
        self.assertEqual(status["mode"], "IDLE")
        self.assertFalse(status["game_taps_enabled"])
        self.assertFalse(status["background_loop"])
        self.assertFalse(status["timer_running"])

    def test_analyse_mode_allows_only_analyse(self):
        status = self.manager.set_mode("ANALYSE")
        self.assertEqual(status["mode"], "ANALYSE")
        self.assertTrue(self.manager.can_process("ANALYSE"))
        self.assertFalse(self.manager.can_process("PLAY"))
        self.assertFalse(self.manager.can_process("LEARN"))

    def test_play_mode_blocked_while_taps_disabled(self):
        with self.assertRaises(PermissionError) as ctx:
            self.manager.set_mode("PLAY")
        self.assertIn("PLAY mode blocked", str(ctx.exception))
        self.assertEqual(self.manager.mode, Mode.IDLE)
        self.assertFalse(self.manager.game_taps_enabled)

    def test_unknown_mode_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            self.manager.set_mode("INVALID")
        self.assertIn("Unknown operating mode", str(ctx.exception))
        self.assertEqual(self.manager.mode, Mode.IDLE)

    def test_pause_blocks_processing_and_resume_returns_to_idle(self):
        self.manager.set_mode("ANALYSE")
        self.manager.pause()
        self.assertEqual(self.manager.mode, Mode.PAUSED)
        self.assertFalse(self.manager.can_process("ANALYSE"))
        self.assertFalse(self.manager.can_process("LEARN"))

        status = self.manager.resume()
        self.assertEqual(status["mode"], "IDLE")
        self.assertEqual(self.manager.mode, Mode.IDLE)

    def test_cannot_leave_paused_except_via_resume_to_idle(self):
        self.manager.pause()
        with self.assertRaises(RuntimeError) as ctx:
            self.manager.set_mode("ANALYSE")
        self.assertIn("Resume to IDLE", str(ctx.exception))
        self.assertEqual(self.manager.mode, Mode.PAUSED)

    def test_stop_returns_to_idle(self):
        self.manager.set_mode("LEARN")
        status = self.manager.stop()
        self.assertEqual(status["mode"], "IDLE")
        self.assertEqual(self.manager.mode, Mode.IDLE)

    def test_can_process_play_requires_both_mode_and_taps(self):
        # Even if mode were PLAY, taps must be enabled; they never are.
        self.assertFalse(self.manager.can_process("PLAY"))
        # Direct assignment is not the public API; safety is enforced in set_mode.
        self.manager.mode = Mode.PLAY
        self.assertFalse(self.manager.can_process("PLAY"))
        self.assertFalse(self.manager.game_taps_enabled)

    def test_case_insensitive_mode_and_task_names(self):
        self.manager.set_mode("analyse")
        self.assertEqual(self.manager.mode, Mode.ANALYSE)
        self.assertTrue(self.manager.can_process("analyse"))
        self.assertTrue(self.manager.can_process("ANALYSE"))

    def test_status_last_task_seconds_non_negative(self):
        self.manager.set_mode("ANALYSE")
        self.manager.stop()
        status = self.manager.status()
        self.assertGreaterEqual(status["last_task_seconds"], 0.0)


if __name__ == "__main__":
    unittest.main()
