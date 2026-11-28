import unittest
from conveyor_geometry import calculate_firing_geometry, DIRECTIONS


class ConveyorGeometryTests(unittest.TestCase):
    def setUp(self):
        self.image_size = (1080, 2220)
        self.board_bounds = (201, 431, 881, 1113)
        self.grid_size = (35, 35)

    def test_known_segments_return_expected_directions(self):
        for segment, expected in DIRECTIONS.items():
            result = calculate_firing_geometry(
                screen_center=(500, 500),
                segment=segment,
                image_size=self.image_size,
                board_bounds=self.board_bounds,
                grid_size=self.grid_size,
            )
            self.assertEqual(result["direction"], expected)
            self.assertEqual(result["segment"], segment)
            self.assertFalse(result["game_taps_enabled"])
            self.assertTrue(result["verified_direction"])

    def test_position_verified_flag_is_respected(self):
        unverified = calculate_firing_geometry(
            (500, 500), "bottom", self.image_size,
            position_verified=False,
        )
        verified = calculate_firing_geometry(
            (500, 500), "bottom", self.image_size,
            position_verified=True,
        )
        self.assertFalse(unverified["verified_screen_position"])
        self.assertTrue(verified["verified_screen_position"])
        self.assertFalse(unverified["game_taps_enabled"])
        self.assertFalse(verified["game_taps_enabled"])

    def test_unknown_segment_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            calculate_firing_geometry((500, 500), "diagonal", self.image_size)
        self.assertIn("Unknown conveyor segment", str(ctx.exception))

    def test_non_two_dimensional_coordinates_rejected(self):
        with self.assertRaises(ValueError):
            calculate_firing_geometry((500,), "bottom", self.image_size)
        with self.assertRaises(ValueError):
            calculate_firing_geometry((500, 500, 0), "bottom", self.image_size)

    def test_invalid_image_dimensions_rejected(self):
        with self.assertRaises(ValueError):
            calculate_firing_geometry((500, 500), "bottom", (0, 2220))
        with self.assertRaises(ValueError):
            calculate_firing_geometry((500, 500), "bottom", (1080, -1))

    def test_invalid_grid_dimensions_rejected(self):
        with self.assertRaises(ValueError):
            calculate_firing_geometry(
                (500, 500), "bottom", self.image_size,
                grid_size=(0, 35),
            )
        with self.assertRaises(ValueError):
            calculate_firing_geometry(
                (500, 500), "bottom", self.image_size,
                grid_size=(35, 0),
            )

    def test_first_board_cell_is_clamped_inside_grid(self):
        # Far outside the board on the bottom side should still produce a valid first cell
        result = calculate_firing_geometry(
            screen_center=(-1000, 3000),
            segment="bottom",
            image_size=self.image_size,
            board_bounds=self.board_bounds,
            grid_size=self.grid_size,
        )
        fx, fy = result["first_board_cell"]
        self.assertGreaterEqual(fx, 0)
        self.assertLess(fx, self.grid_size[0])
        self.assertGreaterEqual(fy, 0)
        self.assertLess(fy, self.grid_size[1])

    def test_safety_flags_always_disabled(self):
        result = calculate_firing_geometry(
            (540, 1110), "bottom", self.image_size
        )
        self.assertFalse(result["game_taps_enabled"])
        self.assertIn("verified_direction", result)
        self.assertIn("verified_screen_position", result)


if __name__ == "__main__":
    unittest.main()
