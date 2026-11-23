import json
import tempfile
import unittest
from pathlib import Path

from observation_region_audit import audit_observation


class ObservationRegionAuditTests(unittest.TestCase):
    def setUp(self):
        self.data = {
            "image_size": [300, 200],
            "grid_size": [3, 2],
            "bounds": [10, 10, 290, 190],
            "board": [
                ["cyan", "cyan", "white"],
                ["cyan", "white", "white"],
            ],
            "raw_rgb": [
                [[10, 180, 230], [10, 180, 230], [245, 245, 245]],
                [[10, 180, 230], [245, 245, 245], [245, 245, 245]],
            ],
            "counts": {"cyan": 3, "white": 3},
            "source_sha256": "c" * 64,
            "snapshot_id": "sha256:" + "c" * 64,
            "board_snapshot_id": "sha256:" + "c" * 64,
            "gameplay_verified": False,
            "vision_classification_verified": False,
            "game_taps_enabled": False,
        }

    def test_builds_region_graph_from_screenshot_observation(self):
        report = audit_observation(self.data)
        self.assertEqual(report["total_cells"], 6)
        self.assertEqual(report["region_count"], 2)
        self.assertEqual(report["component_counts"], {"cyan": 1, "white": 1})
        self.assertEqual(report["snapshot_id"], self.data["snapshot_id"])
        self.assertTrue(all(report["integrity_checks"].values()))

    def test_diagonal_cells_do_not_merge_regions(self):
        data = dict(self.data)
        data["board"] = [
            ["cyan", "white", "cyan"],
            ["white", "cyan", "white"],
        ]
        data["raw_rgb"] = [
            [[10, 180, 230], [245, 245, 245], [10, 180, 230]],
            [[245, 245, 245], [10, 180, 230], [245, 245, 245]],
        ]
        data["counts"] = {"cyan": 3, "white": 3}
        report = audit_observation(data)
        self.assertEqual(report["region_count"], 6)

    def test_rejects_saved_colour_count_mismatch(self):
        self.data["counts"]["cyan"] = 99
        with self.assertRaisesRegex(ValueError, "colour counts"):
            audit_observation(self.data)

    def test_keeps_gameplay_and_colour_truth_unverified(self):
        report = audit_observation(self.data)
        self.assertFalse(report["colour_truth_verified"])
        self.assertFalse(report["shooter_mapping_verified"])
        self.assertFalse(report["planning_authorized"])
        self.assertFalse(report["gameplay_verified"])
        self.assertFalse(report["game_taps_enabled"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
