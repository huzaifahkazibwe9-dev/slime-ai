import copy
import unittest

from game_state import GameState, Shooter
from conveyor_simulator import SimulatorConfig
from capacity_aware_evolving_planner import (
    plan_capacity_aware_evolving_schedule,
)


def make_state(second_accessible=False):
    return GameState(
        board=[["red", "blue", None]],
        shooters={
            "A": Shooter(
                "A", "red", 1, "right", -1, 0, accessible=True,
                group_id="A",
            ),
            "B": Shooter(
                "B", "blue", 1, "right", -1, 0,
                accessible=second_accessible, group_id="B",
            ),
        },
    )


class CapacityAwareEvolvingPlannerTests(unittest.TestCase):
    def test_newly_exposed_group_is_scheduled_in_later_batch(self):
        state = make_state()
        def resolver(current):
            return ["A"] if current.board[0][0] == "red" else ["B"]

        before = copy.deepcopy(state)
        report = plan_capacity_aware_evolving_schedule(
            state,
            accessibility_resolver=resolver,
            config=SimulatorConfig(conveyor_capacity=1, ticks_per_lap=4),
            max_nodes=20,
            beam_width=10,
        )
        self.assertTrue(report["schedule_valid"])
        self.assertEqual(report["simulated_remaining_pixels"], 0)
        self.assertEqual(
            [batch["groups"] for batch in report["batches"]],
            [["A"], ["B"]],
        )
        self.assertTrue(report["full_level_complete"])
        self.assertEqual(state, before)
        self.assertFalse(report["evidence_verified"])
        self.assertFalse(report["live_execution_allowed"])
        self.assertFalse(report["game_taps_enabled"])

    def test_no_resolver_does_not_invent_newly_exposed_access(self):
        report = plan_capacity_aware_evolving_schedule(
            make_state(),
            config=SimulatorConfig(conveyor_capacity=1, ticks_per_lap=4),
            max_nodes=20,
            beam_width=10,
        )
        self.assertFalse(report["full_level_complete"])
        self.assertIn("DYNAMIC_ACCESSIBILITY_UNVERIFIED", report["blockers"])
        self.assertIn("B", report["unplanned_group_ids"])
        self.assertFalse(report["game_taps_enabled"])

    def test_bonded_group_larger_than_conveyor_is_rejected(self):
        state = GameState(
            board=[[None]],
            shooters={
                "A": Shooter(
                    "A", "red", 0, "right", -1, 0,
                    accessible=True, bonded_ids=["B"], group_id="PAIR",
                ),
                "B": Shooter(
                    "B", "red", 0, "right", -1, 0,
                    accessible=True, bonded_ids=["A"], group_id="PAIR",
                ),
            },
        )
        report = plan_capacity_aware_evolving_schedule(
            state,
            config=SimulatorConfig(conveyor_capacity=1, ticks_per_lap=3),
        )
        self.assertFalse(report["schedule_valid"])
        self.assertFalse(report["full_level_complete"])
        self.assertFalse(report["game_taps_enabled"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
