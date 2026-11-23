
import unittest
from region_graph import build_region_graph
from region_lane_mapper import map_lane_regions, audit_observation


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

    def test_screenshot_observation_maps_lane_and_provisional_confidence(self):
        board = [["white"] * 35 for _ in range(35)]
        board[2][15] = "red"
        rgb = [
            [[245, 245, 245] for _ in range(35)]
            for _ in range(35)
        ]
        rgb[2][15] = [230, 30, 30]
        data = {
            "image_size": [1080, 2220],
            "grid_size": [35, 35],
            "bounds": [201, 431, 881, 1113],
            "board": board,
            "raw_rgb": rgb,
            "counts": {"white": 1224, "red": 1},
            "source_sha256": "f" * 64,
            "snapshot_id": "sha256:" + "f" * 64,
            "board_snapshot_id": "sha256:" + "f" * 64,
            "gameplay_verified": False,
            "vision_classification_verified": False,
            "game_taps_enabled": False,
        }
        calibration = {
            "verified_by_user": True,
            "image_size": [1080, 2220],
            "shooters": [{
                "id": "top_1",
                "segment": "top",
                "center": [500, 179],
            }],
            "directions": {"top": "down"},
        }
        observations = {
            "observations": [{
                "position_id": "top_1",
                "colour": "white",
                "ammo": 40,
            }]
        }
        report = audit_observation(data, calibration, observations)
        self.assertEqual(report["grid_size"], [35, 35])
        self.assertEqual(report["confidence_summary"]["requires_confirmation"], 136)
        self.assertEqual(report["confidence_summary"]["provisional"], 1089)
        self.assertEqual(report["confidence_summary"]["confirmed"], 0)
        scenario = report["positions"][0]["scenarios"][0]
        self.assertEqual(scenario["exposed_matching_count"], 2)
        self.assertEqual(
            scenario["exposed_cells"][0]["board_confidence"],
            "requires_confirmation",
        )
        self.assertFalse(report["board_colour_truth_verified"])
        self.assertFalse(report["planning_authorized"])
        self.assertFalse(report["game_taps_enabled"])

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
