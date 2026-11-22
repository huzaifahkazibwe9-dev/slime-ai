import unittest
from region_graph import build_region_graph


class RegionGraphTests(unittest.TestCase):
    def test_single_region_has_no_neighbors(self):
        report = build_region_graph([["a", "a"], ["a", "a"]])
        self.assertEqual(report["region_count"], 1)
        self.assertEqual(report["regions"][0]["neighbor_count"], 0)

    def test_two_regions_share_border(self):
        report = build_region_graph([["a", "b"], ["a", "b"]])
        self.assertEqual(report["region_count"], 2)
        self.assertEqual(len(report["adjacency_edges"]), 1)
        self.assertEqual(report["adjacency_edges"][0]["shared_border"], 2)

    def test_diagonal_same_colour_cells_are_separate_regions(self):
        report = build_region_graph([["a", "b"], ["b", "a"]])
        self.assertEqual(report["region_count"], 4)
        self.assertTrue(all(r["size"] == 1 for r in report["regions"]))
        self.assertEqual(len(report["adjacency_edges"]), 4)

        colours = {r["id"]: r["colour"] for r in report["regions"]}
        for edge in report["adjacency_edges"]:
            self.assertNotEqual(
                colours[edge["region_a"]],
                colours[edge["region_b"]]
            )

    def test_perimeter_of_two_by_two_region(self):
        report = build_region_graph([["a", "a"], ["a", "a"]])
        self.assertEqual(report["regions"][0]["perimeter"], 8)

    def test_sizes_cover_all_cells(self):
        report = build_region_graph([["a", "b", "b"], ["a", "c", "b"]])
        self.assertEqual(sum(x["size"] for x in report["regions"]), 6)
        self.assertTrue(report["checks"]["region_sizes_sum_to_board"])

    def test_adjacency_is_symmetric(self):
        report = build_region_graph([["a", "b"], ["c", "b"]])
        self.assertTrue(report["checks"]["adjacency_is_symmetric"])

    def test_gameplay_stays_disabled(self):
        report = build_region_graph([["a"]])
        self.assertFalse(report["gameplay_verified"])
        self.assertFalse(report["game_taps_enabled"])

    def test_rejects_ragged_board(self):
        with self.assertRaises(ValueError):
            build_region_graph([["a", "b"], ["c"]])


if __name__ == "__main__":
    unittest.main()
