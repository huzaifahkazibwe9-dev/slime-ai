import unittest
from edge_confidence import analyze_board

class EdgeConfidenceTests(unittest.TestCase):
    def setUp(self):
        self.board = [
            ["a", "b", "c", "d"],
            ["e", "f", "g", "h"],
            ["i", "j", "k", "l"],
            ["m", "n", "o", "p"]
        ]
        self.report = analyze_board(self.board)

    def test_cell_counts(self):
        self.assertEqual(self.report["total_cells"], 16)
        self.assertEqual(self.report["boundary_cells"], 12)
        self.assertEqual(self.report["interior_cells"], 4)

    def test_all_colours_and_positions_preserved(self):
        for r, row in enumerate(self.board):
            for c, colour in enumerate(row):
                cell = self.report["cells"][r][c]
                self.assertEqual(cell["colour"], colour)
                self.assertEqual(cell["row"], r)
                self.assertEqual(cell["column"], c)

    def test_boundary_requires_confirmation(self):
        for r, row in enumerate(self.report["cells"]):
            for c, cell in enumerate(row):
                boundary = r in (0, 3) or c in (0, 3)
                self.assertEqual(cell["is_boundary"], boundary)
                if boundary:
                    self.assertEqual(
                        cell["confidence"], "requires_confirmation"
                    )

    def test_interior_is_provisional(self):
        for r in range(1, 3):
            for c in range(1, 3):
                self.assertEqual(
                    self.report["cells"][r][c]["confidence"],
                    "provisional"
                )

    def test_ragged_board_rejected(self):
        with self.assertRaises(ValueError):
            analyze_board([["a", "b"], ["c"]])

    def test_safety_flags_remain_false(self):
        self.assertTrue(self.report["all_cells_preserved"])
        self.assertFalse(self.report["tile_removals_verified"])
        self.assertFalse(self.report["board_transition_verified"])
        self.assertFalse(self.report["game_taps_enabled"])

if __name__ == "__main__":
    unittest.main(verbosity=2)
