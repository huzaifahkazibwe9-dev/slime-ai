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

    def test_reports_copy_and_stage_performance_metrics(self):
        report = simulate_dynamic_multi_batch(
            make_state(),
            [{"groups": ["A"]}, {"groups": ["B"]}],
            SimulatorConfig(conveyor_capacity=1, ticks_per_lap=4),
        )
        metrics = report["performance"]
        self.assertGreater(metrics["deepcopy_calls"], 0)
        self.assertGreater(metrics["group_simulation_calls"], 0)
        self.assertGreater(metrics["board_copy_calls"], 0)
        self.assertGreaterEqual(metrics["board_copy_seconds"], 0)
        self.assertGreaterEqual(metrics["deepcopy_seconds"], 0)
        self.assertGreaterEqual(metrics["group_simulation_seconds"], 0)
        self.assertGreaterEqual(metrics["scheduler_seconds"], 0)
        self.assertEqual(metrics["timing_clock"], "time.perf_counter")

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

    def test_simulation_completion_requires_zero_pixels_and_all_groups(self):
        complete = simulate_dynamic_multi_batch(
            make_state(),
            [{"groups": ["A"]}, {"groups": ["B"]}],
            SimulatorConfig(conveyor_capacity=1, ticks_per_lap=4),
        )
        self.assertTrue(complete["simulation_complete"])
        self.assertTrue(complete["all_known_groups_scheduled"])
        self.assertEqual(complete["unscheduled_group_ids"], [])
        self.assertFalse(complete["full_level_complete"])
        self.assertFalse(complete["live_level_completion_verified"])
        self.assertFalse(complete["conveyor_timing_calibrated"])

        partial = simulate_dynamic_multi_batch(
            make_state(),
            [{"groups": ["A"]}],
            SimulatorConfig(conveyor_capacity=1, ticks_per_lap=4),
        )
        self.assertFalse(partial["simulation_complete"])
        self.assertFalse(partial["all_known_groups_scheduled"])
        self.assertEqual(partial["unscheduled_group_ids"], ["B"])
        self.assertFalse(partial["full_level_complete"])

    def test_rejected_dynamic_schedule_cannot_claim_simulation_complete(self):
        report = simulate_dynamic_multi_batch(
            make_state(),
            [{"groups": ["A"]}, {"groups": ["A"]}],
            SimulatorConfig(conveyor_capacity=2, ticks_per_lap=4),
        )
        self.assertFalse(report["simulation_complete"])
        self.assertFalse(report["all_known_groups_scheduled"])
        self.assertFalse(report["full_level_complete"])
        self.assertFalse(report["live_level_completion_verified"])
        self.assertFalse(report["conveyor_timing_calibrated"])

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
        self.assertFalse(report["simulation_complete"])
        self.assertFalse(report["full_level_complete"])
        self.assertFalse(report["live_level_completion_verified"])

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

    def test_groups_accessible_at_batch_start_can_share_batch(self):
        state = make_state()
        calls = []
        def resolver(current):
            calls.append(current.remaining_pixels)
            return ["A", "B"]
        report = simulate_dynamic_multi_batch(
            state, [{"groups": ["A", "B"]}],
            SimulatorConfig(conveyor_capacity=2, ticks_per_lap=4),
            accessibility_resolver=resolver,
        )
        self.assertEqual(report["status"], "SIMULATED")
        self.assertEqual(report["simulated_remaining_pixels"], 0)
        self.assertEqual(calls, [2])

    def test_group_unlocked_mid_batch_is_rejected_until_next_batch(self):
        state = make_state()
        state.shooters["B"].accessible = False
        calls = []
        def resolver(current):
            calls.append(current.remaining_pixels)
            return ["A"] if current.board[0][0] == "red" else ["B"]
        report = simulate_dynamic_multi_batch(
            state, [{"groups": ["A", "B"]}],
            SimulatorConfig(conveyor_capacity=2, ticks_per_lap=4),
            accessibility_resolver=resolver,
        )
        self.assertEqual(report["status"], "SIMULATION_INCOMPLETE")
        self.assertEqual(
            report["failure"]["reason"],
            "GROUP_NOT_ACCESSIBLE_AT_BATCH_START",
        )
        self.assertEqual(calls, [2])
        self.assertFalse(report["game_taps_enabled"])

    def test_duplicate_group_within_batch_is_rejected(self):
        report = simulate_dynamic_multi_batch(
            make_state(),
            [{"groups": ["A", "A"]}],
            SimulatorConfig(conveyor_capacity=2, ticks_per_lap=4),
        )
        self.assertEqual(report["status"], "SIMULATION_INCOMPLETE")
        self.assertEqual(
            report["failure"]["reason"], "DUPLICATE_GROUP_IN_BATCH"
        )
        self.assertEqual(report["group_simulations"], [])
        self.assertFalse(report["game_taps_enabled"])

    def test_group_cannot_be_scheduled_again_in_later_batch(self):
        report = simulate_dynamic_multi_batch(
            make_state(),
            [{"groups": ["A"]}, {"groups": ["A"]}],
            SimulatorConfig(conveyor_capacity=2, ticks_per_lap=4),
        )
        self.assertEqual(report["status"], "SIMULATION_INCOMPLETE")
        self.assertEqual(
            report["failure"]["reason"], "GROUP_SCHEDULED_MORE_THAN_ONCE"
        )
        self.assertEqual(len(report["group_simulations"]), 1)
        self.assertFalse(report["game_taps_enabled"])

    def test_resolver_mapping_result_is_rejected(self):
        with self.assertRaises(TypeError):
            simulate_dynamic_multi_batch(
                make_state(), [{"groups": ["A"]}],
                accessibility_resolver=lambda current: {"A": True},
            )

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
