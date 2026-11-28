"""Unit tests for sequential_firing_simulator pure offline logic.

These tests exercise validate_board, validate_shooter, simulate_shooter,
and simulate_sequence with synthetic boards only. They do not load private
Level 39 fixtures, perform gameplay actions, or modify caller boards.
"""

import copy
import unittest

from sequential_firing_simulator import (
    simulate_sequence,
    simulate_shooter,
    validate_board,
    validate_shooter,
)


def _shooter(direction="top_down", lane=0, colour="cyan", ammo=5, shooter_id=None):
    shooter = {
        "direction": direction,
        "lane": lane,
        "colour": colour,
        "ammo": ammo,
    }
    if shooter_id is not None:
        shooter["id"] = shooter_id
    return shooter


class SequentialFiringSimulatorTests(unittest.TestCase):
    def test_sequential_shooters_expose_and_clear_later_targets(self):
        board = [["cyan"], ["white"], ["cyan"]]
        original = copy.deepcopy(board)
        shooters = [
            _shooter("top_down", 0, "cyan", 5, "cyan_first"),
            _shooter("top_down", 0, "white", 5, "white_second"),
            _shooter("top_down", 0, "cyan", 5, "cyan_third"),
        ]

        result = simulate_sequence(board, shooters)

        self.assertEqual(result["total_pixels_removed"], 3)
        self.assertEqual(result["remaining_pixels"], 0)
        self.assertEqual(result["results"][0]["status"], "BLOCKED_BY_DIFFERENT_COLOUR")
        self.assertEqual(result["results"][2]["removed_count"], 1)
        self.assertEqual(board, original)
        self.assertTrue(result["original_board_unchanged"])
        self.assertFalse(result["gameplay_actions_performed"])

    def test_empty_cells_do_not_consume_ammunition(self):
        board = [["cyan"], ["cyan"], ["white"]]
        result = simulate_sequence(board, [
            _shooter("top_down", 0, "cyan", 2),
            _shooter("bottom_up", 0, "white", 2),
        ])

        self.assertEqual(result["total_pixels_removed"], 3)
        self.assertEqual(result["remaining_pixels"], 0)

    def test_ammunition_limit_is_respected(self):
        board = [["cyan"], ["cyan"], ["cyan"]]
        result = simulate_sequence(board, [_shooter("top_down", 0, "cyan", 1)])

        first = result["results"][0]
        self.assertEqual(first["shots_used"], 1)
        self.assertEqual(first["status"], "AMMO_EXHAUSTED")
        self.assertEqual(first["remaining_ammo"], 0)
        self.assertEqual(first["removed_count"], 1)

    def test_different_colour_blocks_first_shot(self):
        board = [["white"], ["cyan"]]
        result = simulate_sequence(board, [_shooter("top_down", 0, "cyan", 5)])

        first = result["results"][0]
        self.assertEqual(first["removed_count"], 0)
        self.assertEqual(first["status"], "BLOCKED_BY_DIFFERENT_COLOUR")
        self.assertEqual(first["shots_used"], 0)

    def test_all_four_directions_clear_matching_cells(self):
        cases = [
            ("top_down", [["cyan"], ["cyan"]], 0, 2),
            ("bottom_up", [["cyan"], ["cyan"]], 0, 2),
            ("left_right", [["cyan", "cyan"]], 0, 2),
            ("right_left", [["cyan", "cyan"]], 0, 2),
        ]
        for direction, board, lane, expected in cases:
            with self.subTest(direction=direction):
                result = simulate_sequence(board, [_shooter(direction, lane, "cyan", 5)])
                self.assertEqual(result["total_pixels_removed"], expected)
                self.assertEqual(result["remaining_pixels"], 0)
                self.assertEqual(result["results"][0]["status"], "LANE_CLEARED")

    def test_empty_sequence_leaves_board_unchanged(self):
        board = [["cyan"]]
        result = simulate_sequence(board, [])

        self.assertEqual(result["total_pixels_removed"], 0)
        self.assertEqual(result["remaining_pixels"], 1)
        self.assertEqual(result["shooters_simulated"], 0)
        self.assertTrue(result["original_board_unchanged"])

    def test_invalid_ammunition_is_rejected(self):
        with self.assertRaises(ValueError):
            simulate_sequence([["cyan"]], [_shooter(ammo=-1)])

    def test_firing_stops_at_board_boundary(self):
        board = [["cyan"], ["cyan"]]
        result = simulate_sequence(board, [_shooter("top_down", 0, "cyan", 10)])

        first = result["results"][0]
        self.assertEqual(first["status"], "LANE_CLEARED")
        self.assertEqual(first["removed_count"], 2)
        self.assertEqual(result["remaining_pixels"], 0)

    def test_non_rectangular_board_rejected(self):
        with self.assertRaises(ValueError):
            validate_board([["cyan", "white"], ["cyan"]])

    def test_empty_board_rejected(self):
        with self.assertRaises(ValueError):
            validate_board([])
        with self.assertRaises(ValueError):
            validate_board([[]])

    def test_invalid_direction_rejected(self):
        with self.assertRaises(ValueError):
            validate_shooter(_shooter(direction="diagonal"))

    def test_boolean_and_float_ammo_rejected(self):
        with self.assertRaises(ValueError):
            validate_shooter(_shooter(ammo=True))
        with self.assertRaises(ValueError):
            validate_shooter(_shooter(ammo=1.5))

    def test_lane_out_of_range_rejected(self):
        with self.assertRaises(ValueError):
            simulate_shooter([["cyan"]], _shooter(lane=5), 1)
        with self.assertRaises(ValueError):
            simulate_shooter([["cyan"]], _shooter(direction="left_right", lane=2), 1)

    def test_colour_matching_is_case_insensitive_and_strips(self):
        board = [["  Cyan  "], ["CYAN"]]
        result = simulate_sequence(board, [_shooter(colour="cyan", ammo=5)])

        self.assertEqual(result["total_pixels_removed"], 2)
        self.assertEqual(result["remaining_pixels"], 0)

    def test_zero_ammo_exhausts_immediately_on_occupied_cell(self):
        board = [["cyan"]]
        result = simulate_sequence(board, [_shooter(ammo=0)])

        first = result["results"][0]
        self.assertEqual(first["shots_used"], 0)
        self.assertEqual(first["status"], "AMMO_EXHAUSTED")
        self.assertEqual(first["removed_count"], 0)

    def test_source_board_immutable_after_successful_clear(self):
        board = [["cyan", None], [None, "white"]]
        original = copy.deepcopy(board)
        simulate_sequence(board, [
            _shooter("top_down", 0, "cyan", 1),
            _shooter("left_right", 1, "white", 1),
        ])
        self.assertEqual(board, original)


if __name__ == "__main__":
    unittest.main()
