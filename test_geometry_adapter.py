import unittest

from game_state import Shooter
from geometry_adapter import apply_geometry


class GeometryAdapterSafetyTests(unittest.TestCase):
    def make_shooter(self):
        return Shooter(id="S1", color="cyan", ammo=20, accessible=True)

    def test_requires_explicit_position_confirmation(self):
        shooter = self.make_shooter()
        before = (shooter.x, shooter.y, shooter.direction, shooter.accessible)

        with self.assertRaisesRegex(ValueError, "explicitly verified"):
            apply_geometry(
                shooter, (540, 1200), "bottom", (1080, 2220),
                position_verified=False,
            )

        self.assertEqual(
            (shooter.x, shooter.y, shooter.direction, shooter.accessible),
            before,
        )

    def test_all_four_segments_map_to_expected_virtual_origins(self):
        cases = (
            ((540, 1200), "bottom", "up", (17, 35)),
            ((540, 400), "top", "down", (17, -1)),
            ((900, 700), "right", "left", (35, 13)),
            ((180, 700), "left", "right", (-1, 13)),
        )
        for center, segment, direction, origin in cases:
            with self.subTest(segment=segment):
                shooter = self.make_shooter()
                result = apply_geometry(
                    shooter, center, segment, (1080, 2220),
                    position_verified=True,
                )
                self.assertEqual(shooter.direction, direction)
                self.assertEqual((shooter.x, shooter.y), origin)
                self.assertEqual(result["origin"], origin)
                self.assertTrue(shooter.screen_center_verified)
                self.assertEqual(shooter.screen_center, center)
                self.assertFalse(shooter.accessible)
                self.assertFalse(result["game_taps_enabled"])

    def test_invalid_geometry_does_not_partially_mutate_shooter(self):
        shooter = self.make_shooter()
        before = (
            shooter.x, shooter.y, shooter.direction,
            shooter.screen_center, shooter.screen_center_verified,
            shooter.accessible,
        )

        with self.assertRaises(ValueError):
            apply_geometry(
                shooter, (540, 1200), "diagonal", (1080, 2220),
                position_verified=True,
            )

        self.assertEqual(
            (
                shooter.x, shooter.y, shooter.direction,
                shooter.screen_center, shooter.screen_center_verified,
                shooter.accessible,
            ),
            before,
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
