import unittest

from game_state import GameState, Shooter
from execution_engine import run_dry_simulation


class Build11OIntegrationTests(unittest.TestCase):

    def make_state(self, storage=None):
        shooters = {
            "R": Shooter(
                "R", "red", 1, "right", -1, 0,
                accessible=True
            )
        }

        stored = storage or []
        for sid in stored:
            shooters[sid] = Shooter(
                sid, "blue", 1, "left", 0, 0
            )

        return GameState(
            board=[["red"]],
            shooters=shooters,
            conveyor=[],
            storage=stored,
        )

    def test_successful_storage_return_is_safe(self):
        state = self.make_state()
        report = run_dry_simulation(state)
        candidate = report["best"]

        self.assertIsNotNone(candidate)
        self.assertTrue(candidate["conveyor_safe"])
        simulation = candidate["conveyor_simulation"]
        self.assertFalse(simulation["failed"])
        self.assertEqual(simulation["returned_shooters"], ["R"])
        self.assertEqual(simulation["storage_occupied"], 1)

    def test_full_storage_marks_candidate_unsafe(self):
        state = self.make_state(
            storage=["S1", "S2", "S3", "S4", "S5"]
        )
        report = run_dry_simulation(state)
        candidate = report["best"]

        self.assertIsNotNone(candidate)
        self.assertFalse(candidate["conveyor_safe"])
        simulation = candidate["conveyor_simulation"]
        self.assertTrue(simulation["failed"])
        self.assertIn("STORAGE_IS_FULL", simulation["failure_reason"])
        self.assertEqual(simulation["storage_occupied"], 5)

    def test_integration_never_enables_live_actions(self):
        state = self.make_state()
        report = run_dry_simulation(state)
        candidate = report["best"]

        self.assertFalse(report["live_execution_allowed"])
        self.assertFalse(report["gameplay_actions_performed"])
        self.assertTrue(candidate["conveyor_simulation"]["simulation_only"])
        self.assertFalse(
            candidate["conveyor_simulation"]["live_actions_performed"]
        )
        self.assertFalse(
            candidate["conveyor_simulation"]["live_taps_enabled"]
        )

    def test_original_game_state_remains_unchanged(self):
        state = self.make_state()
        before_board = [row[:] for row in state.board]
        before_storage = list(state.storage)
        before_ammo = {
            key: shooter.ammo
            for key, shooter in state.shooters.items()
        }

        run_dry_simulation(state)

        self.assertEqual(state.board, before_board)
        self.assertEqual(state.storage, before_storage)
        self.assertEqual(
            {key: shooter.ammo for key, shooter in state.shooters.items()},
            before_ammo,
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
