import copy
import unittest

from execution_engine import run_dry_simulation
from game_state import GameState, Shooter


class Build11ADExecutionIntegrationTests(unittest.TestCase):
    def make_bonded_state(self):
        a = Shooter(
            "A", "red", 2, "right", -1, 0,
            accessible=True, group_id="pair", bonded_ids=["B"]
        )
        b = Shooter(
            "B", "blue", 2, "left", 2, 1,
            accessible=False, group_id="pair", bonded_ids=["A"]
        )
        return GameState(
            board=[
                ["red", None, None],
                [None, "blue", None],
            ],
            shooters={"A": a, "B": b},
        )

    def test_dynamic_bonded_simulator_is_integrated(self):
        report = run_dry_simulation(self.make_bonded_state())
        self.assertEqual(report["status"], "SIMULATED")
        best = report["best"]
        self.assertEqual(best["groups"], [["A", "B"]])
        self.assertEqual(len(best["bonded_group_simulations"]), 1)
        self.assertTrue(
            best["bonded_group_simulations"][0]["dynamic_regions_rebuilt"]
        )
        self.assertTrue(best["dynamic_regions_rebuilt"])

    def test_group_members_fire_and_update_candidate_board(self):
        report = run_dry_simulation(self.make_bonded_state())
        best = report["best"]
        self.assertEqual(best["pixels_removed"], 2)
        self.assertEqual(best["remaining_pixels"], 0)
        self.assertEqual(
            {item["shooter_id"] for item in best["firing"]},
            {"A", "B"},
        )

    def test_source_state_remains_unchanged(self):
        state = self.make_bonded_state()
        before = copy.deepcopy(state)
        report = run_dry_simulation(state)
        self.assertTrue(report["source_state_unchanged"])
        self.assertEqual(state, before)

    def test_live_gameplay_remains_disabled(self):
        report = run_dry_simulation(self.make_bonded_state())
        self.assertFalse(report["live_execution_allowed"])
        self.assertFalse(report["gameplay_actions_performed"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
