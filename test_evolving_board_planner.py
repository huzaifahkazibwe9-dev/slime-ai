import copy
import unittest

from game_state import GameState, Shooter
from evolving_board_planner import plan_evolving_board


class EvolvingBoardPlannerTests(unittest.TestCase):
    def test_newly_exposed_group_can_become_available_via_resolver(self):
        state = GameState(
            board=[["red", "blue"]],
            shooters={
                "A": Shooter("A", "red", 1, "right", -1, 0, accessible=True),
                "B": Shooter("B", "blue", 1, "right", -1, 0, accessible=False),
            },
        )

        def resolver(current):
            # Test-only observation model: B is exposed after red is cleared.
            return ["A"] if current.board[0][0] is not None else ["B"]

        before = copy.deepcopy(state)
        report = plan_evolving_board(
            state, accessibility_resolver=resolver,
            max_nodes=20, beam_width=10,
        )
        self.assertEqual(report["status"], "BOARD_SEQUENCE_FOUND")
        self.assertEqual(report["simulated_remaining_pixels"], 0)
        self.assertEqual(
            [item["shooter_ids"] for item in report["sequence"]],
            [["A"], ["B"]],
        )
        self.assertTrue(report["source_state_unchanged"])
        self.assertEqual(state, before)
        self.assertFalse(report["full_level_complete"])
        self.assertFalse(report["game_taps_enabled"])

    def test_without_resolver_does_not_invent_new_accessibility(self):
        state = GameState(
            board=[["red", "blue"]],
            shooters={
                "A": Shooter("A", "red", 1, "right", -1, 0, accessible=True),
                "B": Shooter("B", "blue", 1, "right", 2, 0, accessible=False),
            },
        )
        report = plan_evolving_board(state, max_nodes=20, beam_width=10)
        self.assertEqual(report["status"], "PARTIAL_SEQUENCE")
        self.assertGreater(report["simulated_remaining_pixels"], 0)
        self.assertIn("DYNAMIC_ACCESSIBILITY_UNVERIFIED", report["blockers"])

    def test_search_limits_are_enforced(self):
        state = GameState(
            board=[["red"]],
            shooters={"A": Shooter("A", "red", 1, "right", -1, 0, accessible=True)},
        )
        report = plan_evolving_board(state, max_nodes=1, beam_width=1)
        self.assertLessEqual(report["nodes_examined"], 1)
        self.assertFalse(report["game_taps_enabled"])

    def test_rejects_invalid_limits(self):
        state = GameState([["red"]])
        with self.assertRaises(ValueError):
            plan_evolving_board(state, max_nodes=0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
