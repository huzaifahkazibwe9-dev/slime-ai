#!/usr/bin/env python3
"""Unit tests for firing_adapter pure offline logic.

These tests do not depend on private data files.
"""

import unittest

from game_state import GameState
from firing_adapter import evaluate_lane_target, DIRECTION_MAP


def make_state(height=35, width=35, fills=None):
    board = [[None] * width for _ in range(height)]
    if fills:
        for (x, y), colour in fills.items():
            board[y][x] = colour
    return GameState(board)


class TestFiringAdapter(unittest.TestCase):
    def test_top_down_matches_first_cell(self):
        state = make_state(fills={(4, 0): "cyan"})
        result = evaluate_lane_target(state, "top_down", 4, "cyan")
        self.assertEqual(result["status"], "MATCH")
        self.assertEqual(result["cell"], (4, 0))
        self.assertEqual(result["simulator_direction"], "top_down")
        self.assertEqual(result["lane"], 4)
        self.assertEqual(result["entry_cell"], (4, 0))

    def test_bottom_up_matches(self):
        state = make_state(fills={(4, 34): "cyan"})
        result = evaluate_lane_target(state, "bottom_up", 4, "cyan")
        self.assertEqual(result["status"], "MATCH")
        self.assertEqual(result["cell"], (4, 34))
        self.assertEqual(result["entry_cell"], (4, 34))

    def test_left_right_matches(self):
        state = make_state(fills={(0, 7): "cyan"})
        result = evaluate_lane_target(state, "left_right", 7, "cyan")
        self.assertEqual(result["status"], "MATCH")
        self.assertEqual(result["cell"], (0, 7))
        self.assertEqual(result["entry_cell"], (0, 7))

    def test_right_left_matches(self):
        state = make_state(fills={(34, 7): "cyan"})
        result = evaluate_lane_target(state, "right_left", 7, "cyan")
        self.assertEqual(result["status"], "MATCH")
        self.assertEqual(result["cell"], (34, 7))
        self.assertEqual(result["entry_cell"], (34, 7))

    def test_different_colour_blocks(self):
        state = make_state(fills={(4, 0): "white", (4, 1): "cyan"})
        result = evaluate_lane_target(state, "top_down", 4, "cyan")
        self.assertEqual(result["status"], "BLOCKED_BY_DIFFERENT_COLOUR")
        self.assertEqual(result["cell"], (4, 0))

    def test_empty_lane_no_target(self):
        state = make_state()
        result = evaluate_lane_target(state, "top_down", 4, "cyan")
        self.assertEqual(result["status"], "NO_TARGET")
        self.assertIsNone(result["cell"])

    def test_unverified_colour(self):
        state = make_state(fills={(4, 0): "cyan"})
        result = evaluate_lane_target(state, "top_down", 4, None)
        self.assertEqual(result["status"], "TARGET_FOUND_COLOUR_UNVERIFIED")
        self.assertEqual(result["cell"], (4, 0))

    def test_case_insensitive_match(self):
        state = make_state(fills={(4, 0): "Cyan"})
        result = evaluate_lane_target(state, "top_down", 4, "CYAN")
        self.assertEqual(result["status"], "MATCH")

    def test_unsupported_direction(self):
        state = make_state()
        with self.assertRaises(ValueError) as cm:
            evaluate_lane_target(state, "diagonal", 0)
        self.assertIn("Unsupported simulator direction", str(cm.exception))

    def test_non_integer_lane(self):
        state = make_state()
        with self.assertRaises(ValueError):
            evaluate_lane_target(state, "top_down", 4.0)
        with self.assertRaises(ValueError):
            evaluate_lane_target(state, "top_down", "4")

    def test_boolean_lane_rejected(self):
        state = make_state()
        with self.assertRaises(ValueError):
            evaluate_lane_target(state, "top_down", True)
        with self.assertRaises(ValueError):
            evaluate_lane_target(state, "top_down", False)

    def test_lane_out_of_range(self):
        state = make_state()
        with self.assertRaises(ValueError) as cm:
            evaluate_lane_target(state, "top_down", 35)
        self.assertIn("Lane must be between", str(cm.exception))
        with self.assertRaises(ValueError):
            evaluate_lane_target(state, "top_down", -1)
        with self.assertRaises(ValueError):
            evaluate_lane_target(state, "left_right", 35)

    def test_lane_zero_boundary(self):
        state = make_state(fills={(0, 0): "red"})
        result = evaluate_lane_target(state, "top_down", 0, "red")
        self.assertEqual(result["status"], "MATCH")
        self.assertEqual(result["entry_cell"], (0, 0))

    def test_lane_max_boundary(self):
        state = make_state(fills={(34, 0): "red"})
        result = evaluate_lane_target(state, "top_down", 34, "red")
        self.assertEqual(result["status"], "MATCH")

    def test_direction_map_completeness(self):
        self.assertEqual(set(DIRECTION_MAP.keys()),
                         {"top_down", "bottom_up", "left_right", "right_left"})

    def test_board_immutability(self):
        fills = {(4, 0): "cyan"}
        state = make_state(fills=fills)
        original = [row[:] for row in state.board]
        evaluate_lane_target(state, "top_down", 4, "cyan")
        self.assertEqual(state.board, original)


if __name__ == "__main__":
    unittest.main()
