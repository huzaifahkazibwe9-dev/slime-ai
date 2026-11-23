import copy
import unittest

from game_state import GameState, Shooter
from conveyor_simulator import SimulatorConfig
from dynamic_multi_batch import simulate_dynamic_multi_batch


def make_state():
    # A clears the red tile first. B can then reach the blue tile
    # that was behind it from the opposite direction.
    board = [["red", "blue", None]]
    shooters = {
        "A": Shooter(
            id="A", color="red", ammo=1,
            direction="right", x=-1, y=0, accessible=True,
        ),
        "B": Shooter(
            id="B", color="blue", ammo=1,
            direction="left", x=3, y=0, accessible=True,
        ),
    }
    return GameState(board=board, shooters=shooters)


class Build11AETests(unittest.TestCase):
    def test_board_updates_between_batches(self):
        state = make_state()
        report = simulate_dynamic_multi_batch(
            state,
            [{"groups": ["A"]}, {"groups": ["B"]}],
            SimulatorConfig(conveyor_capacity=1, ticks_per_lap=4),
        )
        self.assertEqual(report["status"], "SIMULATED")
        self.assertTrue(report["schedule_valid"])
        self.assertEqual(report["simulated_pixels_removed"], 2)
        self.assertEqual(report["simulated_remaining_pixels"], 0)
        self.assertEqual(
            report["prepared_batches"][1]["shots"]["B"], 1
        )

    def test_shots_are_calculated_not_supplied(self):
        report = simulate_dynamic_multi_batch(
            make_state(),
            [
                {"groups": ["A"], "shots": {"A": 0}},
                {"groups": ["B"], "shots": {"B": 0}},
            ],
            SimulatorConfig(conveyor_capacity=1, ticks_per_lap=4),
        )
        self.assertEqual(report["prepared_batches"][0]["shots"]["A"], 1)
        self.assertEqual(report["prepared_batches"][1]["shots"]["B"], 1)

    def test_original_state_remains_unchanged(self):
        state = make_state()
        before = copy.deepcopy(state)
        report = simulate_dynamic_multi_batch(
            state,
            [{"groups": ["A"]}, {"groups": ["B"]}],
            SimulatorConfig(conveyor_capacity=1, ticks_per_lap=4),
        )
        self.assertTrue(report["source_state_unchanged"])
        self.assertEqual(state, before)

    def test_live_gameplay_stays_disabled(self):
        report = simulate_dynamic_multi_batch(
            make_state(),
            [{"groups": ["A"]}, {"groups": ["B"]}],
            SimulatorConfig(conveyor_capacity=1, ticks_per_lap=4),
        )
        self.assertFalse(report["live_execution_allowed"])
        self.assertFalse(report["gameplay_actions_performed"])
        self.assertFalse(report["game_taps_enabled"])



    def test_storage_reactivation_is_rejected_until_board_state_is_modelled(self):
        report = simulate_dynamic_multi_batch(
            make_state(),
            [
                {"groups": ["A"]},
                {"groups": ["B"], "reactivate_groups": ["A"]},
            ],
            SimulatorConfig(conveyor_capacity=2, ticks_per_lap=4),
            allow_storage_reactivation=True,
        )
        self.assertEqual(report["status"], "SIMULATION_INCOMPLETE")
        self.assertEqual(
            report["failure"]["reason"],
            "DYNAMIC_STORAGE_REACTIVATION_NOT_SUPPORTED",
        )
        self.assertFalse(report["live_execution_allowed"])
        self.assertFalse(report["game_taps_enabled"])

    def test_explicit_resolver_unlocks_group_after_board_changes(self):
        state = make_state()
        state.shooters["B"].accessible = False
        def resolver(current):
            return ["A"] if current.board[0][0] == "red" else ["B"]
        report = simulate_dynamic_multi_batch(
            state, [{"groups": ["A"]}, {"groups": ["B"]}],
            SimulatorConfig(conveyor_capacity=1, ticks_per_lap=4),
            accessibility_resolver=resolver,
        )
        self.assertEqual(report["status"], "SIMULATED")
        self.assertTrue(report["schedule_valid"])
        self.assertEqual(report["simulated_remaining_pixels"], 0)
        self.assertTrue(report["dynamic_accessibility_resolver_used"])
        self.assertFalse(report["game_taps_enabled"])

    def test_dynamic_accessibility_is_not_invented_without_resolver(self):
        state = make_state()
        state.shooters["B"].accessible = False
        report = simulate_dynamic_multi_batch(
            state, [{"groups": ["A"]}, {"groups": ["B"]}],
            SimulatorConfig(conveyor_capacity=1, ticks_per_lap=4),
        )
        self.assertEqual(report["status"], "SIMULATION_INCOMPLETE")
        self.assertEqual(
            report["failure"]["reason"], "DYNAMIC_GROUP_SIMULATION_FAILED"
        )
        self.assertFalse(report["game_taps_enabled"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
