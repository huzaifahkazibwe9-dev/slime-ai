import json
import unittest
from pathlib import Path
from colour_mapping_auditor import audit

LEVEL39_FILES = (
    Path("data/vision_level39.json"),
    Path("data/shooter_detection.json"),
    Path("data/color_matches.json"),
)

class ColourMappingAuditorTests(unittest.TestCase):
    def setUp(self):
        self.board = {
            "grid_size": [2, 2],
            "board": [
                ["white", "cyan"],
                ["purple", "orange"]
            ],
            "raw_rgb": [
                [[255,255,255], [113,212,254]],
                [[232,47,245], [208,128,67]]
            ]
        }
        self.shooters = {
            "visible_shooters": [
                {"id":"top_1","color":{"name":"white","rgb":[240,240,240]}},
                {"id":"top_2","color":{"name":"cyan","rgb":[104,195,233]}},
                {"id":"top_3","color":{"name":"magenta","rgb":[225,43,237]}},
                {"id":"top_4","color":{"name":"brown","rgb":[193,121,63]}}
            ]
        }
        self.mappings = {
            "mappings": {
                "top_1":{"board_colour":"white","status":"visual_candidate"},
                "top_2":{"board_colour":"cyan","status":"visual_candidate"},
                "top_3":{"board_colour":"purple","status":"visual_candidate"},
                "top_4":{"board_colour":"orange","status":"visual_candidate"}
            }
        }

    def test_all_four_candidates_match(self):
        result = audit(self.board, self.shooters, self.mappings)
        self.assertEqual(
            [x["best_candidate"] for x in result["results"]],
            ["white", "cyan", "purple", "orange"]
        )

    def test_all_four_results_present(self):
        result = audit(self.board, self.shooters, self.mappings)
        self.assertEqual(len(result["results"]), 4)

    def test_existing_candidates_agree(self):
        result = audit(self.board, self.shooters, self.mappings)
        for item in result["results"]:
            self.assertEqual(
                item["existing_candidate"], item["best_candidate"]
            )

    def test_evidence_does_not_claim_gameplay_verification(self):
        result = audit(self.board, self.shooters, self.mappings)
        self.assertFalse(result["gameplay_verified"])
        self.assertFalse(result["gameplay_taps_enabled"])
        self.assertTrue(all(not x["verified"] for x in result["results"]))

    @unittest.skipUnless(
        all(path.is_file() for path in LEVEL39_FILES),
        "Private Level 39 evidence is not included in the public repository"
    )
    def test_actual_level39_data(self):
        board = json.loads(LEVEL39_FILES[0].read_text())
        shooters = json.loads(LEVEL39_FILES[1].read_text())
        mappings = json.loads(LEVEL39_FILES[2].read_text())
        result = audit(board, shooters, mappings)
        self.assertEqual(len(result["results"]), 4)
        self.assertEqual(
            [x["best_candidate"] for x in result["results"]],
            ["white", "cyan", "purple", "orange"]
        )

    def test_empty_shooters_keeps_safety_flags_false(self):
        empty_shooters = {"visible_shooters": []}
        result = audit(self.board, empty_shooters, self.mappings)
        self.assertEqual(result["results"], [])
        self.assertFalse(result["gameplay_verified"])
        self.assertFalse(result["gameplay_taps_enabled"])
        self.assertIn("warning", result)


    def test_missing_visible_shooters_raises(self):
        with self.assertRaises(KeyError):
            audit(self.board, {}, self.mappings)

    def test_missing_shooter_color_raises(self):
        bad_shooters = {"visible_shooters": [{"id": "top_1"}]}
        with self.assertRaises(KeyError):
            audit(self.board, bad_shooters, self.mappings)

    def test_empty_board_profiles_raises_on_rankings(self):
        empty_board = {
            "grid_size": [0, 0],
            "board": [],
            "raw_rgb": []
        }
        with self.assertRaises(IndexError):
            audit(empty_board, self.shooters, self.mappings)

    def test_missing_mappings_key_raises(self):
        with self.assertRaises(KeyError):
            audit(self.board, self.shooters, {})

if __name__ == "__main__":
    unittest.main(verbosity=2)

    def test_missing_visible_shooters_raises(self):
        with self.assertRaises(KeyError):
            audit(self.board, {}, self.mappings)

    def test_missing_shooter_color_raises(self):
        bad_shooters = {"visible_shooters": [{"id": "top_1"}]}
        with self.assertRaises(KeyError):
            audit(self.board, bad_shooters, self.mappings)

    def test_empty_board_profiles_raises_on_rankings(self):
        empty_board = {
            "grid_size": [0, 0],
            "board": [],
            "raw_rgb": []
        }
        with self.assertRaises(IndexError):
            audit(empty_board, self.shooters, self.mappings)

    def test_missing_mappings_key_raises(self):
        with self.assertRaises(KeyError):
            audit(self.board, self.shooters, {})
