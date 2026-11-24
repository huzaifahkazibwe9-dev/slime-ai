import unittest

from conveyor_geometry import calculate_firing_geometry


class ConveyorGeometryInputValidationTests(unittest.TestCase):
    def calculate(self, **overrides):
        values = {
            "screen_center": (540, 1200),
            "segment": "bottom",
            "image_size": (1080, 2220),
            "position_verified": True,
        }
        values.update(overrides)
        return calculate_firing_geometry(**values)

    def test_accepts_valid_geometry(self):
        result = self.calculate()
        self.assertEqual(result["direction"], "up")
        self.assertFalse(result["game_taps_enabled"])

    def test_rejects_non_string_segment(self):
        for value in (None, 1, ["bottom"]):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "segment must be a string"):
                    self.calculate(segment=value)

    def test_rejects_malformed_or_non_finite_screen_center(self):
        for value in (None, "540,1100", (540,), (540, float("nan")),
                      (540, float("inf")), (True, 1100), (object(), 1100)):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "Screen center"):
                    self.calculate(screen_center=value)

    def test_rejects_malformed_or_non_positive_image_size(self):
        for value in (None, "1080x2220", (1080,), (1080, float("inf")),
                      (1080, True), (1080, 0), (-1, 2220)):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    self.calculate(image_size=value)

    def test_rejects_malformed_or_degenerate_board_bounds(self):
        for value in (None, (1, 2, 3), (1, 2, 1, 4),
                      (1, 2, 3, float("nan")), "1,2,3,4"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    self.calculate(board_bounds=value)

    def test_rejects_non_integer_or_non_positive_grid_dimensions(self):
        for value in (None, (35,), (35, 0), (35, -1), (35, True), (35.0, 35)):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "Grid size"):
                    self.calculate(grid_size=value)

    def test_rejects_image_dimensions_that_underflow_scaled_board_cells(self):
        with self.assertRaises(ValueError):
            self.calculate(image_size=(5e-324, 5e-324))

    def test_extreme_integer_input_is_rejected_without_overflow(self):
        with self.assertRaisesRegex(ValueError, "Screen center"):
            self.calculate(screen_center=(10 ** 1000, 1))


    def test_rejects_centers_outside_screenshot_bounds(self):
        for center in ((-1, 1200), (1080, 1200), (540, -1), (540, 2220)):
            with self.subTest(center=center):
                with self.assertRaisesRegex(ValueError, "outside screenshot bounds"):
                    self.calculate(screen_center=center)


if __name__ == "__main__":
    unittest.main(verbosity=2)
