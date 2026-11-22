
import unittest
from region_graph import build_region_graph
from region_lane_mapper import map_lane_regions


class RegionLaneMapperTests(unittest.TestCase):
    def setUp(self):
        self.board = [
            ["red", "green", "red", "blue"],
            ["green", "green", "blue", "blue"],
        ]
        self.graph = build_region_graph(self.board)

    def test_region_graph_has_coordinate_grid(self):
        grid = self.graph["cell_region_ids"]
        self.assertEqual(len(grid), 2)
        self.assertEqual(len(grid[0]), 4)
        self.assertNotEqual(grid[0][0], grid[0][2])

    def test_exposed_cells_map_to_regions(self):
        report = map_lane_regions(self.board, self.graph, {
            "results": [{
                "position_id": "test",
                "scenarios": [{
                    "target_colour": "red",
                    "exposed_matching_cells": [
                        {"row": 0, "column": 0, "colour": "red"}
                    ],
                    "matching_tiles_behind_blocker": [],
                    "lane_cells": [],
                    "first_blocker": None,
                }],
            }]
        })
        scenario = report["positions"][0]["scenarios"][0]
        self.assertEqual(scenario["exposed_matching_count"], 1)
        self.assertEqual(len(scenario["exposed_region_ids"]), 1)

    def test_behind_blocker_regions_are_mapped(self):
        report = map_lane_regions(self.board, self.graph, {
            "results": [{
                "scenarios": [{
                    "target_colour": "red",
                    "exposed_matching_cells": [
                        {"row": 0, "column": 0, "colour": "red"}
                    ],
                    "matching_tiles_behind_blocker": [
                        {"row": 0, "column": 2, "colour": "red"}
                    ],
                    "lane_cells": [],
                    "first_blocker": {
                        "row": 0, "column": 1, "colour": "green"
                    },
                }],
            }]
        })
        scenario = report["positions"][0]["scenarios"][0]
        self.assertNotEqual(
            scenario["exposed_region_ids"],
            scenario["behind_blocker_region_ids"],
        )
        self.assertIsNotNone(scenario["first_blocker"]["region_id"])

    def test_confidence_is_preserved(self):
        confidence = [
            ["requires_confirmation", "requires_confirmation",
             "provisional", "provisional"],
            ["provisional"] * 4,
        ]
        report = map_lane_regions(self.board, self.graph, {
            "results": [{
                "scenarios": [{
                    "exposed_matching_cells": [
                        {"row": 0, "column": 0, "colour": "red"}
                    ],
                    "matching_tiles_behind_blocker": [],
                    "lane_cells": [],
                    "first_blocker": None,
                }],
            }]
        }, confidence)
        cell = report["positions"][0]["scenarios"][0]["exposed_cells"][0]
        self.assertEqual(
            cell["board_confidence"], "requires_confirmation"
        )

    def test_out_of_bounds_cell_rejected(self):
        with self.assertRaises(ValueError):
            map_lane_regions(self.board, self.graph, {
                "results": [{
                    "scenarios": [{
                        "exposed_matching_cells": [
                            {"row": 9, "column": 0, "colour": "red"}
                        ],
                    }],
                }]
            })

    def test_gameplay_actions_remain_disabled(self):
        report = map_lane_regions(self.board, self.graph, {"results": []})
        self.assertFalse(report["gameplay_verified"])
        self.assertFalse(report["planning_authorized"])
        self.assertFalse(report["game_taps_enabled"])


if __name__ == "__main__":
    unittest.main()
