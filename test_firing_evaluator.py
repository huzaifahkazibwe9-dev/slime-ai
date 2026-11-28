"""Unit tests for firing_evaluator pure offline path evaluation."""

import unittest

from game_state import GameState
from firing_evaluator import trace_firing_path, evaluate_firing_target


def _board(rows):
    """Helper: rows is list of list of colour or None."""
    return GameState(board=rows)


class TraceFiringPathTests(unittest.TestCase):
    def test_immediate_hit_at_entry(self):
        state = _board([["red"]])
        result = trace_firing_path(state, (0, 0), "right")
        self.assertTrue(result["found"])
        self.assertEqual(result["cell"], (0, 0))
        self.assertEqual(result["colour"], "red")
        self.assertEqual(result["distance"], 0)
        self.assertEqual(result["direction"], "right")

    def test_hit_after_empty_cells_right(self):
        state = _board([[None, None, "blue"]])
        result = trace_firing_path(state, (0, 0), "right")
        self.assertTrue(result["found"])
        self.assertEqual(result["cell"], (2, 0))
        self.assertEqual(result["colour"], "blue")
        self.assertEqual(result["distance"], 2)

    def test_hit_after_empty_cells_down(self):
        state = _board([[None], [None], ["green"]])
        result = trace_firing_path(state, (0, 0), "down")
        self.assertTrue(result["found"])
        self.assertEqual(result["cell"], (0, 2))
        self.assertEqual(result["colour"], "green")
        self.assertEqual(result["distance"], 2)

    def test_hit_left(self):
        state = _board([["yellow", None, None]])
        result = trace_firing_path(state, (2, 0), "left")
        self.assertTrue(result["found"])
        self.assertEqual(result["cell"], (0, 0))
        self.assertEqual(result["colour"], "yellow")
        self.assertEqual(result["distance"], 2)

    def test_hit_up(self):
        state = _board([["purple"], [None], [None]])
        result = trace_firing_path(state, (0, 2), "up")
        self.assertTrue(result["found"])
        self.assertEqual(result["cell"], (0, 0))
        self.assertEqual(result["colour"], "purple")
        self.assertEqual(result["distance"], 2)

    def test_no_target_empty_board(self):
        state = _board([[None, None], [None, None]])
        result = trace_firing_path(state, (0, 0), "right")
        self.assertFalse(result["found"])
        self.assertIsNone(result["cell"])
        self.assertIsNone(result["colour"])
        self.assertIsNone(result["distance"])
        self.assertEqual(result["direction"], "right")

    def test_no_target_exits_bounds(self):
        state = _board([[None, None, None]])
        result = trace_firing_path(state, (0, 0), "right")
        self.assertFalse(result["found"])

    def test_unsupported_direction_raises(self):
        state = _board([["red"]])
        with self.assertRaises(ValueError) as ctx:
            trace_firing_path(state, (0, 0), "diagonal")
        self.assertIn("Unsupported direction", str(ctx.exception))

    def test_path_does_not_mutate_board(self):
        board = [[None, "red"], [None, None]]
        state = _board(board)
        original = [row[:] for row in board]
        trace_firing_path(state, (0, 0), "right")
        self.assertEqual(state.board, original)


class EvaluateFiringTargetTests(unittest.TestCase):
    def test_no_target_status(self):
        state = _board([[None, None]])
        result = evaluate_firing_target(state, (0, 0), "right")
        self.assertEqual(result["status"], "NO_TARGET")
        self.assertIsNone(result["colour_match"])
        self.assertFalse(result["found"])

    def test_colour_unverified_when_shooter_colour_none(self):
        state = _board([["red"]])
        result = evaluate_firing_target(state, (0, 0), "right", shooter_colour=None)
        self.assertEqual(result["status"], "TARGET_FOUND_COLOUR_UNVERIFIED")
        self.assertIsNone(result["colour_match"])
        self.assertTrue(result["found"])
        self.assertEqual(result["colour"], "red")

    def test_match_case_insensitive(self):
        state = _board([["Red"]])
        result = evaluate_firing_target(
            state, (0, 0), "right", shooter_colour="RED"
        )
        self.assertEqual(result["status"], "MATCH")
        self.assertTrue(result["colour_match"])

    def test_match_with_whitespace(self):
        state = _board([["  blue  "]])
        result = evaluate_firing_target(
            state, (0, 0), "right", shooter_colour="Blue"
        )
        self.assertEqual(result["status"], "MATCH")
        self.assertTrue(result["colour_match"])

    def test_blocked_by_different_colour(self):
        state = _board([["green"]])
        result = evaluate_firing_target(
            state, (0, 0), "right", shooter_colour="red"
        )
        self.assertEqual(result["status"], "BLOCKED_BY_DIFFERENT_COLOUR")
        self.assertFalse(result["colour_match"])

    def test_match_after_empty_cells(self):
        state = _board([[None, None, "orange"]])
        result = evaluate_firing_target(
            state, (0, 0), "right", shooter_colour="orange"
        )
        self.assertEqual(result["status"], "MATCH")
        self.assertEqual(result["distance"], 2)
        self.assertEqual(result["cell"], (2, 0))

    def test_blocked_after_empty_cells(self):
        state = _board([[None, "cyan"]])
        result = evaluate_firing_target(
            state, (0, 0), "right", shooter_colour="magenta"
        )
        self.assertEqual(result["status"], "BLOCKED_BY_DIFFERENT_COLOUR")
        self.assertEqual(result["distance"], 1)

    def test_all_four_directions_match(self):
        # Center cell empty; targets in each cardinal direction.
        board = [
            [None, "up_c", None],
            ["left_c", None, "right_c"],
            [None, "down_c", None],
        ]
        state = _board(board)
        cases = [
            ((1, 1), "up", "up_c"),
            ((1, 1), "down", "down_c"),
            ((1, 1), "left", "left_c"),
            ((1, 1), "right", "right_c"),
        ]
        for entry, direction, colour in cases:
            with self.subTest(direction=direction):
                result = evaluate_firing_target(
                    state, entry, direction, shooter_colour=colour
                )
                self.assertEqual(result["status"], "MATCH")
                self.assertEqual(result["colour"], colour)

    def test_does_not_mutate_state(self):
        board = [[None, "red"], [None, None]]
        state = _board(board)
        original = [row[:] for row in board]
        evaluate_firing_target(state, (0, 0), "right", shooter_colour="red")
        self.assertEqual(state.board, original)

    def test_unsupported_direction_raises(self):
        state = _board([["red"]])
        with self.assertRaises(ValueError):
            evaluate_firing_target(state, (0, 0), "sideways", shooter_colour="red")


if __name__ == "__main__":
    unittest.main()
