import unittest
from game_state import GameState, Shooter
from region_graph import build_region_graph
from dynamic_board_simulator import inspect_lane, simulate_dynamic_board


class DynamicBoardTests(unittest.TestCase):
    def make_state(self, board, colour="red", ammo=5, direction="right", x=-1, y=0):
        return GameState(
            board=board,
            shooters={"S1": Shooter("S1", colour, ammo, direction, x, y, accessible=True)}
        )

    def test_successive_matching_pixels(self):
        r = simulate_dynamic_board(self.make_state([["red", "red", "red"]]), "S1")
        self.assertEqual(r["pixels_removed"], 3)
        self.assertEqual(r["remaining_ammo"], 2)

    def test_different_colour_blocks(self):
        r = simulate_dynamic_board(self.make_state([["blue", "red"]]), "S1")
        self.assertEqual(r["pixels_removed"], 0)
        self.assertEqual(r["remaining_ammo"], 5)
        self.assertEqual(r["steps"][0]["reason"], "Blocked by another colour")

    def test_empty_cells_are_transparent(self):
        r = simulate_dynamic_board(self.make_state([[None, "red", None]]), "S1")
        self.assertEqual(r["pixels_removed"], 1)
        self.assertIsNone(r["final_board"][0][1])

    def test_source_state_preserved(self):
        state = self.make_state([["red", "red"]])
        before = copy_state = ([row[:] for row in state.board], state.shooters["S1"].ammo)
        r = simulate_dynamic_board(state, "S1")
        self.assertEqual(state.board, before[0])
        self.assertEqual(state.shooters["S1"].ammo, before[1])
        self.assertTrue(r["source_state_unchanged"])

    def test_regions_rebuilt(self):
        r = simulate_dynamic_board(self.make_state([["red", "red", "blue"]]), "S1")
        self.assertEqual(len(r["region_history"]), 2)
        self.assertEqual(r["final_region_graph"]["occupied_cells"], 1)
        self.assertEqual(r["final_region_graph"]["empty_cells"], 2)

    def test_region_graph_handles_empty_cells(self):
        g = build_region_graph([["red", None, "blue"], ["red", None, "blue"]])
        self.assertEqual(g["region_count"], 2)
        self.assertEqual(g["occupied_cells"], 4)
        self.assertEqual(g["empty_cells"], 2)
        self.assertTrue(g["checks"]["all_occupied_cells_assigned"])
        self.assertTrue(g["checks"]["region_sizes_sum_to_board"])

    def test_empty_cell_has_no_region(self):
        g = build_region_graph([["red", None, "blue"]])
        self.assertIsNone(g["cell_region_ids"][0][1])

    def test_lane_blocker(self):
        r = inspect_lane(self.make_state([["blue", "red"]]), "S1")
        self.assertEqual(r["status"], "BLOCKED_BY_DIFFERENT_COLOUR")
        self.assertEqual(r["position"], [0, 0])

    def test_live_actions_disabled(self):
        r = simulate_dynamic_board(self.make_state([["red"]]), "S1")
        self.assertFalse(r["gameplay_verified"])
        self.assertFalse(r["live_execution_allowed"])
        self.assertFalse(r["game_taps_enabled"])

    def test_consume_state_updates_only_disposable_state(self):
        disposable = self.make_state([["red", "red"]])
        untouched = self.make_state([["red", "red"]])
        report = simulate_dynamic_board(disposable, "S1", consume_state=True)
        self.assertEqual(report["status"] if "status" in report else "SIMULATED", "SIMULATED")
        self.assertEqual(disposable.board, report["final_board"])
        self.assertEqual(untouched.board, [["red", "red"]])
        self.assertEqual(untouched.shooters["S1"].ammo, 5)

    def test_consume_state_requires_boolean(self):
        with self.assertRaises(TypeError):
            simulate_dynamic_board(self.make_state([["red"]]), "S1", consume_state=1)

    def test_reports_region_graph_and_shot_profiling(self):
        report = simulate_dynamic_board(self.make_state([["red", "red", "red"]]), "S1")
        metrics = report["performance"]
        self.assertGreater(metrics["region_graph_build_calls"], 0)
        self.assertGreaterEqual(metrics["region_graph_build_seconds"], 0)
        self.assertGreaterEqual(metrics["shot_simulation_seconds"], 0)
        self.assertGreaterEqual(metrics["lane_inspection_seconds"], 0)
        self.assertEqual(metrics["timing_clock"], "time.perf_counter")

    def test_invalid_shot_limit(self):
        with self.assertRaises(ValueError):
            simulate_dynamic_board(self.make_state([["red"]]), "S1", max_shots=0)


if __name__ == "__main__":
    unittest.main()
