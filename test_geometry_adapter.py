#!/usr/bin/env python3
"""Unit tests for geometry_adapter pure offline logic.

These tests do not depend on private calibration files.
"""

import unittest

from game_state import Shooter
from geometry_adapter import apply_geometry


def make_shooter(id_="s1"):
    return Shooter(id=id_, color="test", ammo=10)


class TestGeometryAdapter(unittest.TestCase):
    def setUp(self):
        self.image_size = (1080, 2220)
        self.screen_center = (540, 1800)  # bottom area
        self.segment = "bottom"

    def test_apply_sets_direction_and_origin(self):
        shooter = make_shooter()
        result = apply_geometry(
            shooter,
            self.screen_center,
            self.segment,
            self.image_size,
            position_verified=True,
        )
        self.assertEqual(shooter.direction, "up")
        self.assertEqual((shooter.x, shooter.y), result["origin"])
        self.assertEqual(shooter.screen_center, tuple(self.screen_center))
        self.assertTrue(shooter.screen_center_verified)
        self.assertFalse(shooter.accessible)
        self.assertFalse(result["game_taps_enabled"])

    def test_rejects_unverified_position(self):
        shooter = make_shooter()
        with self.assertRaises(ValueError) as cm:
            apply_geometry(
                shooter,
                self.screen_center,
                self.segment,
                self.image_size,
                position_verified=False,
            )
        self.assertIn("must be explicitly verified", str(cm.exception))
        # shooter remains unchanged
        self.assertFalse(shooter.accessible)
        self.assertFalse(shooter.screen_center_verified)

    def test_rejects_non_true_verified(self):
        shooter = make_shooter()
        for bad in (None, 1, "true", False):
            with self.assertRaises(ValueError):
                apply_geometry(
                    shooter,
                    self.screen_center,
                    self.segment,
                    self.image_size,
                    position_verified=bad,
                )

    def test_all_segments_set_correct_direction(self):
        expected = {
            "bottom": "up",
            "right": "left",
            "top": "down",
            "left": "right",
        }
        for segment, direction in expected.items():
            shooter = make_shooter(id_=segment)
            apply_geometry(
                shooter,
                (540, 1110),
                segment,
                self.image_size,
                position_verified=True,
            )
            self.assertEqual(shooter.direction, direction)
            self.assertFalse(shooter.accessible)

    def test_accessible_remains_false(self):
        shooter = make_shooter()
        shooter.accessible = True  # try to force
        apply_geometry(
            shooter,
            self.screen_center,
            self.segment,
            self.image_size,
            position_verified=True,
        )
        self.assertFalse(shooter.accessible)

    def test_invalid_segment_propagates(self):
        shooter = make_shooter()
        with self.assertRaises(ValueError) as cm:
            apply_geometry(
                shooter,
                self.screen_center,
                "diagonal",
                self.image_size,
                position_verified=True,
            )
        self.assertIn("Unknown conveyor segment", str(cm.exception))

    def test_invalid_image_size_propagates(self):
        shooter = make_shooter()
        with self.assertRaises(ValueError):
            apply_geometry(
                shooter,
                self.screen_center,
                self.segment,
                (0, 100),
                position_verified=True,
            )

    def test_returns_geometry_result(self):
        shooter = make_shooter()
        result = apply_geometry(
            shooter,
            self.screen_center,
            self.segment,
            self.image_size,
            position_verified=True,
        )
        self.assertIn("origin", result)
        self.assertIn("direction", result)
        self.assertIn("first_board_cell", result)
        self.assertEqual(result["direction"], "up")


if __name__ == "__main__":
    unittest.main()
