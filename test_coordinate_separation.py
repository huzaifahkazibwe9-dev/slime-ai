import json
import tempfile
import unittest
from pathlib import Path

from shooter_loader import load_shooters
from geometry_adapter import apply_geometry


class CoordinateSeparationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.detection_file = Path(self.temp_dir.name) / "shooters.json"
        self.detection_file.write_text(json.dumps({
            "visible_shooters": [
                {
                    "id": "top_1", "ammo": 40,
                    "color": {"name": "white", "rgb": [240, 240, 240]},
                    "screen_center": [505, 179],
                    "screen_box": [480, 154, 530, 204]
                },
                {
                    "id": "top_2", "ammo": 40,
                    "color": {"name": "cyan", "rgb": [104, 195, 233]},
                    "screen_center": [595, 183],
                    "screen_box": [570, 158, 620, 208]
                }
            ],
            "bonded_groups": [["top_1", "top_2"]]
        }))

    def test_detection_coordinates_are_panel_coordinates(self):
        shooters = load_shooters(path=self.detection_file)

        for shooter in shooters.values():
            self.assertIsNotNone(shooter.panel_center)
            self.assertIsNotNone(shooter.panel_box)
            self.assertIsNone(shooter.screen_center)
            self.assertIsNone(shooter.screen_box)
            self.assertFalse(shooter.screen_center_verified)
            self.assertFalse(shooter.accessible)

    def test_conveyor_geometry_does_not_overwrite_panel_position(self):
        shooters = load_shooters(path=self.detection_file)
        shooter = shooters["top_1"]
        original_panel_center = shooter.panel_center
        original_panel_box = shooter.panel_box

        apply_geometry(
            shooter=shooter,
            screen_center=(505, 179),
            segment="top",
            image_size=(747, 1536),
            position_verified=True,
        )

        self.assertEqual(shooter.panel_center, original_panel_center)
        self.assertEqual(shooter.panel_box, original_panel_box)
        self.assertEqual(shooter.screen_center, (505, 179))
        self.assertTrue(shooter.screen_center_verified)
        self.assertFalse(shooter.accessible)

    def test_panel_and_conveyor_positions_are_independent(self):
        shooters = load_shooters(path=self.detection_file)
        shooter = shooters["top_2"]

        panel_center = shooter.panel_center

        apply_geometry(
            shooter=shooter,
            screen_center=(600, 190),
            segment="top",
            image_size=(747, 1536),
            position_verified=True,
        )

        self.assertNotEqual(shooter.panel_center, shooter.screen_center)
        self.assertEqual(shooter.panel_center, panel_center)


if __name__ == "__main__":
    unittest.main()
