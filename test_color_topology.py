import unittest
from color_topology import analyze_board


class ColourTopologyTests(unittest.TestCase):
    def test_single_region(self):
        report = analyze_board([["cyan", "cyan"], ["cyan", "cyan"]])
        self.assertEqual(report["component_counts"], {"cyan": 1})
        self.assertEqual(report["components"][0]["size"], 4)

    def test_diagonal_cells_are_separate(self):
        report = analyze_board([["red", "blue"], ["blue", "red"]])
        self.assertEqual(report["component_counts"]["red"], 2)
        self.assertEqual(report["component_counts"]["blue"], 2)

    def test_different_colours_are_separate(self):
        report = analyze_board([["white", "white", "cyan"]])
        self.assertEqual(report["component_counts"]["white"], 1)
        self.assertEqual(report["component_counts"]["cyan"], 1)

    def test_every_cell_is_accounted_for(self):
        report = analyze_board([
            ["a", "a", "b"],
            ["c", "b", "b"],
        ])
        self.assertEqual(report["total_cells"], 6)
        self.assertTrue(report["checks"]["all_cells_accounted_for"])
        self.assertTrue(report["checks"]["colour_counts_reconstructed"])

    def test_rejects_non_rectangular_board(self):
        with self.assertRaises(ValueError):
            analyze_board([["a", "b"], ["c"]])

    def test_gameplay_remains_disabled(self):
        report = analyze_board([["cyan"]])
        self.assertFalse(report["gameplay_verified"])
        self.assertFalse(report["pixel_removal_verified"])
        self.assertFalse(report["game_taps_enabled"])


if __name__ == "__main__":
    unittest.main()
