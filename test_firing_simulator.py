"""Unit tests for firing_simulator pure offline logic.

These tests exercise validate_board and simulate with synthetic boards only.
They do not load private Level 39 fixtures, perform gameplay actions, or
modify caller boards.
"""

import copy
import unittest

from firing_simulator import simulate, validate_board


def _board(fill="cyan", size=35):
    return [[fill] * size for _ in range(size)]


class FiringSimulatorTests(unittest.TestCase):
    def test_matching_cells_are_removed(self):
        board = _board()
        result = simulate(board, "top_down", 4, "cyan", 10)

        self.assertEqual(result["removed_count"], 10)
        self.assertEqual(result["shots_used"], 10)
        self.assertEqual(result["remaining_ammo"], 0)
        self.assertEqual(result["status"], "AMMO_EXHAUSTED")

    def test_different_colour_blocks_firing(self):
        board = _board()
        board[3][4] = "white"
        result = simulate(board, "top_down", 4, "cyan", 10)

        self.assertEqual(result["removed_count"], 3)
        self.assertEqual(result["status"], "BLOCKED_BY_DIFFERENT_COLOUR")
        self.assertEqual(result["next_cell_colour"], "white")
        self.assertEqual(result["shots_used"], 3)

    def test_bottom_up_fires_upward(self):
        board = _board()
        result = simulate(board, "bottom_up", 2, "cyan", 2)

        self.assertEqual(
            result["removed_cells"],
            [
                {"cell": [34, 2], "colour": "cyan"},
                {"cell": [33, 2], "colour": "cyan"},
            ],
        )

    def test_left_right_fires_rightward(self):
        board = _board()
        result = simulate(board, "left_right", 7, "cyan", 3)

        self.assertEqual(
            result["removed_cells"],
            [
                {"cell": [7, 0], "colour": "cyan"},
                {"cell": [7, 1], "colour": "cyan"},
                {"cell": [7, 2], "colour": "cyan"},
            ],
        )

    def test_right_left_fires_leftward(self):
        board = _board()
        result = simulate(board, "right_left", 8, "cyan", 2)

        self.assertEqual(
            result["removed_cells"],
            [
                {"cell": [8, 34], "colour": "cyan"},
                {"cell": [8, 33], "colour": "cyan"},
            ],
        )

    def test_original_board_remains_unchanged(self):
        board = _board()
        original = copy.deepcopy(board)
        simulate(board, "top_down", 0, "cyan", 5)
        self.assertEqual(board, original)

    def test_firing_stops_at_board_boundary(self):
        board = _board()
        result = simulate(board, "top_down", 0, "cyan", 40)

        self.assertEqual(result["removed_count"], 35)
        self.assertEqual(result["status"], "LANE_CLEARED")
        self.assertEqual(result["shots_used"], 35)
        self.assertEqual(result["remaining_ammo"], 5)
        self.assertIsNone(result["next_cell"])

    def test_zero_ammo_exhausts_immediately(self):
        board = _board()
        result = simulate(board, "top_down", 0, "cyan", 0)

        self.assertEqual(result["shots_used"], 0)
        self.assertEqual(result["removed_count"], 0)
        self.assertEqual(result["status"], "AMMO_EXHAUSTED")
        self.assertEqual(result["remaining_ammo"], 0)

    def test_empty_string_colour_rejected(self):
        board = _board()
        with self.assertRaises(ValueError):
            simulate(board, "top_down", 0, "", 1)

    def test_negative_ammo_rejected(self):
        board = _board()
        with self.assertRaises(ValueError):
            simulate(board, "top_down", 0, "cyan", -1)

    def test_boolean_ammo_rejected(self):
        board = _board()
        with self.assertRaises(ValueError):
            simulate(board, "top_down", 0, "cyan", True)

    def test_lane_out_of_range_rejected(self):
        board = _board()
        with self.assertRaises(ValueError):
            simulate(board, "top_down", 35, "cyan", 1)
        with self.assertRaises(ValueError):
            simulate(board, "top_down", -1, "cyan", 1)

    def test_unknown_direction_rejected(self):
        board = _board()
        with self.assertRaises(ValueError):
            simulate(board, "diagonal", 0, "cyan", 1)

    def test_invalid_board_shape_rejected(self):
        with self.assertRaises(ValueError):
            validate_board([["cyan"] * 35])  # too few rows
        with self.assertRaises(ValueError):
            validate_board([["cyan"] * 34 for _ in range(35)])  # short row
        with self.assertRaises(ValueError):
            validate_board([[1] * 35 for _ in range(35)])  # non-string cell

    def test_simulated_board_has_none_for_removed_cells(self):
        board = _board()
        result = simulate(board, "top_down", 0, "cyan", 2)
        simulated = result["simulated_board"]
        self.assertIsNone(simulated[0][0])
        self.assertIsNone(simulated[1][0])
        self.assertEqual(simulated[2][0], "cyan")
        # Caller board unchanged
        self.assertEqual(board[0][0], "cyan")


if __name__ == "__main__":
    unittest.main()
