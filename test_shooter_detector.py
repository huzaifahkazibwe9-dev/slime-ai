import unittest

from shooter_detector import (
    REF_W,
    REF_H,
    identify_color,
    scale_box,
    scale_point,
    validate_panel_image_size,
)


class ShooterDetectorCalibrationTests(unittest.TestCase):
    def test_reference_panel_dimensions_are_valid(self):
        self.assertTrue(validate_panel_image_size(REF_W, REF_H))

    def test_user_panel_crop_aspect_ratio_is_valid(self):
        self.assertTrue(validate_panel_image_size(830, 540))

    def test_full_phone_screenshot_is_rejected_as_panel_crop(self):
        with self.assertRaisesRegex(ValueError, "aspect ratio"):
            validate_panel_image_size(1080, 2220)

    def test_invalid_dimensions_are_rejected(self):
        with self.assertRaises(ValueError):
            validate_panel_image_size(0, 540)

    def test_scaled_panel_sample_coordinates(self):
        sx = 830 / REF_W
        sy = 540 / REF_H
        self.assertEqual(scale_point((330, 275), sx, sy), (178, 149))

    def test_scaled_ocr_box_stays_in_crop(self):
        sx = 830 / REF_W
        sy = 540 / REF_H
        box = scale_box((235, 150, 435, 285), sx, sy)
        self.assertTrue(0 <= box[0] < box[2] <= 830)
        self.assertTrue(0 <= box[1] < box[3] <= 540)

    def test_brown_shooter_colour_is_distinguished_from_orange(self):
        self.assertEqual(identify_color((193, 126, 63))["name"], "brown")
        self.assertEqual(identify_color((230, 140, 50))["name"], "orange")


if __name__ == "__main__":
    unittest.main(verbosity=2)
