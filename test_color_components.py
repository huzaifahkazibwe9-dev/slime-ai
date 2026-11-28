"""Unit tests for color_components pure offline logic.

These tests exercise find_components with synthetic boards only.
They do not load private Level 39 fixtures or perform gameplay actions.
"""

import unittest

from color_components import find_components


class ColorComponentsTests(unittest.TestCase):
    def test_diagonal_cells_remain_separate(self):
        board = [
            ["red", "blue"],
            ["blue", "red"],
        ]
        result = find_components(board)

        self.assertEqual(len(result["red"]), 2)
        self.assertEqual(len(result["blue"]), 2)
        for group in result.values():
            for item in group:
                self.assertEqual(item["size"], 1)

    def test_orthogonal_adjacent_cells_form_one_component(self):
        board = [
            ["red", "red"],
            ["blue", "red"],
        ]
        result = find_components(board)

        self.assertEqual(len(result["red"]), 1)
        self.assertEqual(result["red"][0]["size"], 3)
        self.assertEqual(len(result["blue"]), 1)
        self.assertEqual(result["blue"][0]["size"], 1)

    def test_single_cell_component(self):
        board = [["cyan"]]
        result = find_components(board)

        self.assertEqual(len(result["cyan"]), 1)
        item = result["cyan"][0]
        self.assertEqual(item["size"], 1)
        self.assertEqual(item["bounds"], [0, 0, 0, 0])
        self.assertTrue(item["touches_board_edge"])
        self.assertEqual(item["sample_cells"], [[0, 0]])

    def test_empty_board(self):
        board = []
        result = find_components(board)
        self.assertEqual(result, {})

    def test_multiple_components_same_colour_sorted_by_size(self):
        board = [
            ["red", "red", "blue", "red"],
            ["blue", "blue", "blue", "red"],
            ["red", "blue", "red", "red"],
        ]
        result = find_components(board)

        reds = result["red"]
        self.assertGreaterEqual(len(reds), 2)
        sizes = [item["size"] for item in reds]
        self.assertEqual(sizes, sorted(sizes, reverse=True))

    def test_edge_touching_detected(self):
        board = [
            ["cyan", "green"],
            ["green", "cyan"],
        ]
        result = find_components(board)
        for colour, items in result.items():
            for item in items:
                self.assertTrue(item["touches_board_edge"])

    def test_internal_component_does_not_touch_edge(self):
        # 3x3 with center cell different
        board = [
            ["a", "a", "a"],
            ["a", "b", "a"],
            ["a", "a", "a"],
        ]
        result = find_components(board)
        self.assertEqual(len(result["b"]), 1)
        self.assertFalse(result["b"][0]["touches_board_edge"])
        self.assertTrue(result["a"][0]["touches_board_edge"])

    def test_bounds_calculation(self):
        board = [
            ["x", "x", "y"],
            ["x", "y", "y"],
            ["y", "y", "y"],
        ]
        result = find_components(board)
        # Largest x component
        x_item = result["x"][0]
        self.assertEqual(x_item["bounds"][0], 0)  # min row
        self.assertEqual(x_item["bounds"][1], 0)  # min col
        self.assertGreaterEqual(x_item["bounds"][2], 1)  # max row
        self.assertGreaterEqual(x_item["bounds"][3], 1)  # max col

    def test_sample_cells_limited_to_eight(self):
        # Create a long snake of the same colour
        board = [["red"] * 10 for _ in range(2)]
        result = find_components(board)
        self.assertEqual(len(result["red"]), 1)
        self.assertEqual(result["red"][0]["size"], 20)
        self.assertEqual(len(result["red"][0]["sample_cells"]), 8)

    def test_none_and_empty_string_treated_as_distinct_colours(self):
        board = [
            [None, ""],
            ["", None],
        ]
        result = find_components(board)
        self.assertIn(None, result)
        self.assertIn("", result)
        self.assertEqual(len(result[None]), 2)
        self.assertEqual(len(result[""]), 2)

    def test_rectangular_non_square_board(self):
        board = [
            ["a", "a", "b"],
            ["b", "a", "b"],
        ]
        result = find_components(board)
        self.assertEqual(result["a"][0]["size"], 3)
        self.assertEqual(len(result["b"]), 2)


if __name__ == "__main__":
    unittest.main()
