import json
import unittest
from pathlib import Path
from vision_validator import audit_data, classify_rgb as validator_classify_rgb
from screenshot_ingestor import classify_rgb as ingestion_classify_rgb
from vision import classify_rgb as analysis_classify_rgb

class VisionValidatorTests(unittest.TestCase):
    def setUp(self):
        self.data = {
            "grid_size": [2, 2],
            "board": [
                ["white", "red"],
                ["cyan", "orange"]
            ],
            "raw_rgb": [
                [[255, 255, 255], [255, 0, 0]],
                [[0, 255, 255], [255, 128, 0]]
            ],
            "counts": {
                "white": 1, "red": 1, "cyan": 1, "orange": 1
            },
            "occupancy": {
                "initial_occupancy_user_confirmed": True
            }
        }

    def test_all_vision_paths_use_one_shared_classifier(self):
        self.assertIs(validator_classify_rgb, ingestion_classify_rgb)
        self.assertIs(analysis_classify_rgb, ingestion_classify_rgb)
        samples = (
            (245, 245, 245),
            (104, 195, 233),
            (230, 30, 30),
            (200, 120, 60),
            (240, 80, 220),
        )
        for sample in samples:
            with self.subTest(sample=sample):
                expected = ingestion_classify_rgb(sample)
                self.assertEqual(validator_classify_rgb(sample), expected)
                self.assertEqual(analysis_classify_rgb(sample), expected)

    def test_valid_grid(self):
        self.assertTrue(audit_data(self.data)["passed"])

    def test_all_samples_checked(self):
        self.assertEqual(
            audit_data(self.data)["valid_rgb_samples"], 4
        )

    def test_detects_label_mismatch(self):
        self.data["board"][0][0] = "red"
        result = audit_data(self.data)
        self.assertFalse(result["passed"])
        self.assertGreater(result["classification_mismatch_count"], 0)

    def test_detects_invalid_rgb(self):
        self.data["raw_rgb"][0][0] = [300, 0, 0]
        self.assertFalse(audit_data(self.data)["passed"])

    def test_detects_count_mismatch(self):
        self.data["counts"]["white"] = 9
        self.assertFalse(audit_data(self.data)["passed"])

    def test_rejects_invalid_grid_dimensions(self):
        for grid_size in ([True, 2], [2.0, 2], [0, 2], [-1, 2]):
            with self.subTest(grid_size=grid_size):
                self.data["grid_size"] = grid_size
                result = audit_data(self.data)
                self.assertFalse(result["passed"])
                self.assertIn("Invalid grid_size", result["errors"])
        self.data["grid_size"] = [2, 2]

    def test_malformed_counts_and_occupancy_are_handled(self):
        self.data["counts"] = []
        self.data["occupancy"] = []
        result = audit_data(self.data)
        self.assertFalse(result["passed"])
        self.assertFalse(result["initial_occupancy_user_confirmed"])

    def test_safety_flags_remain_disabled(self):
        result = audit_data(self.data)
        self.assertFalse(result["vision_classification_verified"])
        self.assertFalse(result["gameplay_colour_mapping_verified"])
        self.assertFalse(result["gameplay_taps_enabled"])

    def test_actual_level39_data(self):
        path = Path("data/vision_level39.json")
        if not path.exists():
            self.skipTest("Level 39 vision data not found")
        data = json.loads(path.read_text())
        result = audit_data(data)
        self.assertEqual(result["grid_size"], [35, 35])
        self.assertEqual(result["valid_rgb_samples"], 1225)
        self.assertEqual(result["classification_mismatch_count"], 0)
        self.assertTrue(result["saved_counts_match"])

if __name__ == "__main__":
    unittest.main(verbosity=2)
