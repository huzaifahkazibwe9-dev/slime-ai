import unittest

from game_state import GameState, Shooter
from execution_engine import run_multi_batch_schedule
from conveyor_simulator import SimulatorConfig


def make_state():
    board = [[None for _ in range(35)] for _ in range(35)]
    state = GameState(board)
    state.shooters = {
        "A": Shooter(id="A", color="white", ammo=1),
        "B": Shooter(id="B", color="cyan", ammo=1),
    }
    return state


class Build11RTests(unittest.TestCase):

    def test_multi_batch_entry_point(self):
        state = make_state()
        report = run_multi_batch_schedule(
            state,
            [
                {"groups": ["A"], "shots": {"A": 1}},
                {"groups": ["B"], "shots": {"B": 1}},
            ],
            SimulatorConfig(conveyor_capacity=1, ticks_per_lap=4),
        )
        self.assertEqual(
            report["engine"],
            "build11r_execution_engine_multi_batch",
        )
        self.assertTrue(report["schedule_valid"])

    def test_original_state_is_not_modified(self):
        state = make_state()
        before = {
            key: shooter.ammo
            for key, shooter in state.shooters.items()
        }
        run_multi_batch_schedule(
            state,
            [{"groups": ["A"], "shots": {"A": 1}}],
        )
        after = {
            key: shooter.ammo
            for key, shooter in state.shooters.items()
        }
        self.assertEqual(before, after)

    def test_existing_conveyor_is_restored(self):
        state = make_state()
        state.conveyor.append("A")
        report = run_multi_batch_schedule(
            state,
            [],
        )
        self.assertTrue(report["existing_conveyor_restored"])
        self.assertEqual(report["conveyor_occupied"], 1)

    def test_live_actions_remain_disabled(self):
        state = make_state()
        report = run_multi_batch_schedule(
            state,
            [{"groups": ["A"], "shots": {"A": 1}}],
        )
        self.assertFalse(report["live_execution_allowed"])
        self.assertFalse(report["gameplay_actions_performed"])

    def test_non_game_state_rejected(self):
        with self.assertRaises(TypeError):
            run_multi_batch_schedule({}, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
