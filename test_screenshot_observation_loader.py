import json
import runpy
import sys
from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import patch
import tempfile
import unittest
from pathlib import Path

from screenshot_observation_loader import load_observed_level
from level_loader import load_level


class ScreenshotObservationLoaderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.observation_path = self.root / "observation.json"
        self.shooter_path = self.root / "shooters.json"
        board = [
            ["cyan", "white", "cyan"],
            ["orange", "pink", "white"],
        ]
        rgb = [
            [[10, 180, 230], [245, 245, 245], [10, 180, 230]],
            [[200, 120, 60], [240, 80, 220], [245, 245, 245]],
        ]
        self.observation = {
            "image_size": [300, 200],
            "grid_size": [3, 2],
            "bounds": [10, 10, 290, 190],
            "board": board,
            "raw_rgb": rgb,
            "counts": {"cyan": 2, "white": 2, "orange": 1, "pink": 1},
            "source_sha256": "a" * 64,
            "snapshot_id": "sha256:" + "a" * 64,
            "gameplay_verified": False,
            "vision_classification_verified": False,
            "game_taps_enabled": False,
        }
        self.shooters = {
            "visible_shooters": [
                {
                    "id": "top_1", "color": {"name": "white"},
                    "ammo": 40, "screen_center": [50, 20],
                    "screen_box": [10, 5, 90, 35],
                    "bonded_ids": ["top_2"], "verified": False,
                },
                {
                    "id": "top_2", "color": {"name": "cyan"},
                    "ammo": 40, "screen_center": [150, 20],
                    "screen_box": [110, 5, 190, 35],
                    "bonded_ids": ["top_1"], "verified": False,
                },
            ],
            "bonded_groups": [["top_1", "top_2"]],
        }
        self.write()

    def tearDown(self):
        self.temp.cleanup()

    def write(self):
        self.observation_path.write_text(json.dumps(self.observation))
        self.shooter_path.write_text(json.dumps(self.shooters))

    def test_observation_integrates_with_shooter_panel(self):
        state, audit = load_observed_level(
            self.observation_path, self.shooter_path, level=39
        )
        self.assertEqual(state.board, self.observation["board"])
        self.assertEqual(state.width, 3)
        self.assertEqual(state.height, 2)
        self.assertEqual(state.remaining_pixels, 6)
        self.assertEqual(len(state.shooters), 2)
        self.assertEqual(state.shooters["top_1"].bonded_ids, ["top_2"])
        self.assertEqual(state.shooters["top_1"].panel_center, (50, 20))
        self.assertIsNone(state.shooters["top_1"].screen_center)
        self.assertFalse(state.shooters["top_1"].accessible)
        self.assertEqual(state.validate(), [])
        self.assertEqual(audit["snapshot_id"], self.observation["snapshot_id"])

    def test_unified_level_loader_accepts_explicit_screenshot_mode(self):
        state, audit = load_level(
            level=39,
            observation_path=self.observation_path,
            shooter_path=self.shooter_path,
        )
        self.assertEqual(state.level, 39)
        self.assertEqual(state.width, 3)
        self.assertEqual(state.height, 2)
        self.assertEqual(audit["source"], "screenshot_observation")
        self.assertFalse(audit["game_taps_enabled"])

    def test_level_loader_cli_completes_screenshot_mode(self):
        output = StringIO()
        argv = [
            "level_loader.py",
            "--observation", str(self.observation_path),
            "--shooters", str(self.shooter_path),
        ]
        with patch.object(sys, "argv", argv), redirect_stdout(output):
            runpy.run_module("level_loader", run_name="__main__")
        self.assertIn("SCREENSHOT OBSERVATION INTEGRATION PASSED", output.getvalue())
        self.assertIn("Game taps enabled: False", output.getvalue())

    def test_rejects_board_dimensions_that_do_not_match_grid(self):
        self.observation["board"] = [["cyan"]]
        self.write()
        with self.assertRaisesRegex(ValueError, "Board row count"):
            load_observed_level(self.observation_path, self.shooter_path)

    def test_all_verification_and_action_flags_stay_false(self):
        _, audit = load_observed_level(
            self.observation_path, self.shooter_path
        )
        for key in (
            "shooter_positions_gameplay_verified",
            "initial_occupancy_confirmed",
            "vision_classification_verified",
            "colour_mapping_verified",
            "board_transition_verified",
            "gameplay_verified",
            "game_taps_enabled",
        ):
            self.assertFalse(audit[key])
        self.assertTrue(audit["classification_consistent_with_extractor"])
        self.assertFalse(audit["colour_truth_verified"])

    def test_rejects_mismatched_colour_counts(self):
        self.observation["counts"]["cyan"] = 99
        self.write()
        with self.assertRaisesRegex(ValueError, "colour counts"):
            load_observed_level(self.observation_path, self.shooter_path)

    def test_rejects_rgb_and_saved_label_mismatch(self):
        self.observation["board"][0][0] = "red"
        self.write()
        with self.assertRaisesRegex(ValueError, "RGB/classification mismatch"):
            load_observed_level(self.observation_path, self.shooter_path)

    def test_rejects_invalid_rgb_sample(self):
        self.observation["raw_rgb"][0][0] = [256, 0, 0]
        self.write()
        with self.assertRaisesRegex(ValueError, "RGB sample"):
            load_observed_level(self.observation_path, self.shooter_path)

    def test_rejects_snapshot_identity_mismatch(self):
        self.observation["snapshot_id"] = "sha256:" + "b" * 64
        self.write()
        with self.assertRaisesRegex(ValueError, "snapshot identity"):
            load_observed_level(self.observation_path, self.shooter_path)

    def test_rejects_attempt_to_mark_visuals_verified(self):
        self.observation["vision_classification_verified"] = True
        self.write()
        with self.assertRaisesRegex(ValueError, "colours must remain unverified"):
            load_observed_level(self.observation_path, self.shooter_path)

    def test_rejects_attempt_to_enable_game_taps(self):
        self.observation["game_taps_enabled"] = True
        self.write()
        with self.assertRaisesRegex(ValueError, "actions must remain disabled"):
            load_observed_level(self.observation_path, self.shooter_path)


if __name__ == "__main__":
    unittest.main(verbosity=2)
