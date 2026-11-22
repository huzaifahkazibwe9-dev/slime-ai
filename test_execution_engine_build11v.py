
import unittest

from game_state import GameState, Shooter
from execution_engine import run_multi_batch_schedule
from conveyor_simulator import SimulatorConfig


def make_state():
    board = [[None for _ in range(35)] for _ in range(35)]
    return GameState(
        board,
        shooters={
            "A": Shooter(id="A", color="white", ammo=1),
            "B": Shooter(id="B", color="cyan", ammo=1),
        },
    )


def make_batches():
    return [
        {"groups": ["A"], "shots": {"A": 1}},
        {
            "groups": ["A", "B"],
            "reactivate_groups": ["A"],
            "shots": {"A": 0, "B": 1},
        },
    ]


class Build11VTests(unittest.TestCase):

    def test_reactivation_disabled_by_default(self):
        report = run_multi_batch_schedule(
            make_state(),
            make_batches(),
            SimulatorConfig(conveyor_capacity=2, ticks_per_lap=4),
        )
        self.assertFalse(report["schedule_valid"])
        self.assertEqual(
            report["batch_reports"][-1]["reason"],
            "STORAGE_REACTIVATION_NOT_ENABLED",
        )
        self.assertFalse(report["storage_reactivation_enabled"])

    def test_explicit_reactivation_flag_reaches_scheduler(self):
        report = run_multi_batch_schedule(
            make_state(),
            make_batches(),
            SimulatorConfig(conveyor_capacity=2, ticks_per_lap=4),
            allow_storage_reactivation=True,
        )
        self.assertTrue(report["storage_reactivation_enabled"])
        self.assertEqual(
            report["engine"],
            "build11r_execution_engine_multi_batch",
        )

    def test_live_actions_remain_disabled(self):
        report = run_multi_batch_schedule(
            make_state(),
            make_batches(),
            SimulatorConfig(conveyor_capacity=2, ticks_per_lap=4),
            allow_storage_reactivation=True,
        )
        self.assertFalse(report["live_execution_allowed"])
        self.assertFalse(report["gameplay_actions_performed"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
