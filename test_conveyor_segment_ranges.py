import unittest

from conveyor_geometry import calculate_firing_geometry


class ConveyorSegmentRangeTests(unittest.TestCase):
    def calculate(self, center, segment):
        return calculate_firing_geometry(
            screen_center=center,
            segment=segment,
            image_size=(1080, 2220),
            position_verified=True,
        )

    def test_rejects_horizontal_coordinate_outside_top_and_bottom_spans(self):
        for segment, center in (
            ("bottom", (200, 1200)),
            ("bottom", (882, 1200)),
            ("top", (200, 400)),
            ("top", (882, 400)),
        ):
            with self.subTest(segment=segment, center=center):
                with self.assertRaisesRegex(ValueError, "horizontal conveyor span"):
                    self.calculate(center, segment)

    def test_rejects_vertical_coordinate_outside_left_and_right_spans(self):
        for segment, center in (
            ("left", (100, 430)),
            ("left", (100, 1114)),
            ("right", (900, 430)),
            ("right", (900, 1114)),
        ):
            with self.subTest(segment=segment, center=center):
                with self.assertRaisesRegex(ValueError, "vertical conveyor span"):
                    self.calculate(center, segment)

    def test_rejects_centers_on_wrong_side_of_declared_segment(self):
        for segment, center in (
            ("bottom", (540, 1000)),
            ("top", (540, 500)),
            ("right", (850, 700)),
            ("left", (250, 700)),
        ):
            with self.subTest(segment=segment, center=center):
                with self.assertRaises(ValueError):
                    self.calculate(center, segment)

    def test_accepts_centers_on_each_declared_segment(self):
        for segment, center in (
            ("bottom", (540, 1200)),
            ("top", (540, 400)),
            ("right", (900, 700)),
            ("left", (180, 700)),
        ):
            with self.subTest(segment=segment, center=center):
                result = self.calculate(center, segment)
                self.assertFalse(result["game_taps_enabled"])
                self.assertTrue(result["verified_screen_position"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
