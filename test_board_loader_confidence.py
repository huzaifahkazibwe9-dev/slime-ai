import json
import tempfile
import unittest
from pathlib import Path

from board_loader import load_board


class BoardLoaderConfidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

        self.board = [
            ["a", "b", "c", "d"],
            ["e", "f", "g", "h"],
            ["i", "j", "k", "l"],
            ["m", "n", "o", "p"]
        ]

        self.vision_path = self.root / "vision.json"
        self.confidence_path = self.root / "confidence.json"

        self.vision = {
            "grid_size": [4, 4],
            "board": self.board,
            "occupancy": {
                "mask": [[1] * 4 for _ in range(4)],
                "initial_occupancy_user_confirmed": True,
                "colour_classification_verified": False
            }
        }

        self.confidence = {
            "grid_size": [4, 4],
            "total_cells": 16,
            "all_cells_preserved": True,
            "cells": []
        }

        for y, row in enumerate(self.board):
            confidence_row = []
            for x, colour in enumerate(row):
                boundary = (
                    y in (0, 3) or x in (0, 3)
                )
                confidence_row.append({
                    "row": y,
                    "column": x,
                    "colour": colour,
                    "is_boundary": boundary,
                    "confidence": (
                        "requires_confirmation"
                        if boundary else "provisional"
                    )
                })
            self.confidence["cells"].append(confidence_row)

        self.write_files()

    def tearDown(self):
        self.temp.cleanup()

    def write_files(self):
        self.vision_path.write_text(json.dumps(self.vision))
        self.confidence_path.write_text(json.dumps(self.confidence))

    def test_board_and_confidence_load(self):
        result = load_board(self.vision_path, self.confidence_path)
        self.assertEqual(result["board"], self.board)
        self.assertEqual(result["width"], 4)
        self.assertEqual(result["height"], 4)
        self.assertTrue(result["confidence_available"])

    def test_correct_cell_counts(self):
        result = load_board(self.vision_path, self.confidence_path)
        self.assertEqual(result["candidate_pixels"], 16)
        self.assertEqual(result["occupied_pixels"], 16)
        self.assertEqual(result["boundary_cells_needing_confirmation"], 12)
        self.assertEqual(result["interior_provisional_cells"], 4)

    def test_confidence_coordinates_preserved(self):
        result = load_board(self.vision_path, self.confidence_path)
        self.assertEqual(
            result["confidence"][0][0],
            "requires_confirmation"
        )
        self.assertEqual(
            result["confidence"][1][1],
            "provisional"
        )

    def test_colour_mismatch_rejected(self):
        self.confidence["cells"][1][1]["colour"] = "wrong"
        self.write_files()
        with self.assertRaises(ValueError):
            load_board(self.vision_path, self.confidence_path)

    def test_coordinate_mismatch_rejected(self):
        self.confidence["cells"][1][1]["column"] = 3
        self.write_files()
        with self.assertRaises(ValueError):
            load_board(self.vision_path, self.confidence_path)


    def test_non_square_grid_dimensions_use_width_then_height(self):
        board = [["a", "b", "c"], ["d", "e", "f"]]
        self.vision["grid_size"] = [3, 2]
        self.vision["board"] = board
        self.vision["occupancy"]["mask"] = [[1] * 3 for _ in range(2)]
        self.confidence["grid_size"] = [2, 3]
        self.confidence["cells"] = []
        for y, row in enumerate(board):
            confidence_row = []
            for x, colour in enumerate(row):
                boundary = y in (0, 1) or x in (0, 2)
                confidence_row.append({
                    "row": y, "column": x, "colour": colour,
                    "is_boundary": boundary,
                    "confidence": "requires_confirmation" if boundary else "provisional",
                })
            self.confidence["cells"].append(confidence_row)
        self.write_files()
        result = load_board(self.vision_path, self.confidence_path)
        self.assertEqual((result["width"], result["height"]), (3, 2))

    def test_occupancy_mask_rejects_non_binary_and_boolean_values(self):
        for value in (2, -1, True, 0.5):
            with self.subTest(value=value):
                self.vision["occupancy"]["mask"][0][0] = value
                self.write_files()
                with self.assertRaises(ValueError):
                    load_board(self.vision_path, self.confidence_path)
                self.vision["occupancy"]["mask"][0][0] = 1

    def test_non_list_board_row_rejected(self):
        self.vision["board"][1] = 7
        self.write_files()
        with self.assertRaises(ValueError):
            load_board(self.vision_path, self.confidence_path)

    def test_non_dict_occupancy_metadata_rejected(self):
        self.vision["occupancy"] = []
        self.write_files()
        with self.assertRaises(ValueError):
            load_board(self.vision_path, self.confidence_path)

    def test_non_dict_confidence_cell_rejected(self):
        self.confidence["cells"][1][1] = "invalid"
        self.write_files()
        with self.assertRaises(ValueError):
            load_board(self.vision_path, self.confidence_path)

    def test_safety_flags_remain_disabled(self):
        result = load_board(self.vision_path, self.confidence_path)
        self.assertFalse(result["tile_removals_verified"])
        self.assertFalse(result["board_transition_verified"])
        self.assertFalse(result["game_taps_enabled"])
        self.assertFalse(result["verified"])


    def test_board_loader_rejects_duplicate_grid_size_key(self):
        self.write_files()
        raw = self.vision_path.read_text()
        self.vision_path.write_text(
            raw.replace('"grid_size": [3, 2]', '"grid_size": [3, 2], "grid_size": [2, 3]', 1)
        )
        with self.assertRaisesRegex(ValueError, "Duplicate JSON object key"):
            load_board(self.vision_path, self.confidence_path)


if __name__ == "__main__":
    unittest.main(verbosity=2)
