import unittest
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from PIL import Image

from shooter_detector import (
    read_ammunition,
    REF_W,
    REF_H,
    identify_color,
    scale_box,
    scale_point,
    validate_panel_image_size,
    verify_panel_crop,
    extract_panel_crop,
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

    def test_panel_extractor_creates_calibrated_crop_from_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = Image.new("RGB", (400, 300), (30, 80, 120))
            source_path = root / "source.png"
            output_path = root / "panel.jpg"
            source.save(source_path)
            extract_panel_crop(
                source_path, [20, 30, 327, 230], output_path
            )
            with Image.open(output_path) as panel:
                self.assertEqual(panel.size, (REF_W, REF_H))
            digest = verify_panel_crop(
                source_path, output_path, [20, 30, 327, 230]
            )
            self.assertEqual(len(digest), 64)

    def test_panel_extractor_rejects_uncalibrated_aspect_ratio(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_path = root / "source.png"
            Image.new("RGB", (200, 200)).save(source_path)
            with self.assertRaisesRegex(ValueError, "aspect ratio"):
                extract_panel_crop(
                    source_path, [10, 10, 110, 90], root / "panel.jpg"
                )

    def test_panel_crop_is_bound_to_exact_source_screenshot_region(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = Image.new("RGB", (100, 80), (10, 20, 30))
            for x in range(20, 70):
                for y in range(10, 50):
                    source.putpixel((x, y), (x, y, 100))
            source_path = root / "source.png"
            panel_path = root / "panel.png"
            source.save(source_path)
            source.crop((20, 10, 70, 50)).save(panel_path)
            digest = verify_panel_crop(
                source_path, panel_path, [20, 10, 70, 50]
            )
            self.assertEqual(len(digest), 64)

    def test_panel_crop_accepts_resized_jpeg_from_same_source_region(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = Image.new("RGB", (120, 100))
            for x in range(120):
                for y in range(100):
                    source.putpixel((x, y), (x * 2, y * 2, (x + y) % 256))
            source_path = root / "source.png"
            panel_path = root / "panel.jpg"
            source.save(source_path)
            source.crop((10, 10, 110, 90)).resize((200, 160)).save(
                panel_path, quality=85
            )
            digest = verify_panel_crop(
                source_path, panel_path, [10, 10, 110, 90]
            )
            self.assertEqual(len(digest), 64)

    def test_panel_crop_rejects_wrong_aspect_ratio(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            Image.new("RGB", (100, 80), (10, 20, 30)).save(root / "source.png")
            Image.new("RGB", (50, 30), (10, 20, 30)).save(root / "panel.png")
            with self.assertRaisesRegex(ValueError, "aspect ratio"):
                verify_panel_crop(
                    root / "source.png", root / "panel.png",
                    [20, 10, 70, 50]
                )

    def test_panel_crop_rejects_unrelated_image(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            Image.new("RGB", (100, 80), (10, 20, 30)).save(root / "source.png")
            Image.new("RGB", (50, 40), (200, 100, 50)).save(root / "panel.png")
            with self.assertRaisesRegex(ValueError, "does not match"):
                verify_panel_crop(
                    root / "source.png", root / "panel.png",
                    [20, 10, 70, 50]
                )

    def test_panel_crop_rejects_out_of_bounds_region(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            Image.new("RGB", (100, 80)).save(root / "source.png")
            Image.new("RGB", (50, 40)).save(root / "panel.png")
            with self.assertRaisesRegex(ValueError, "outside"):
                verify_panel_crop(
                    root / "source.png", root / "panel.png",
                    [60, 10, 110, 50]
                )

    def test_ammunition_ocr_accepts_one_unambiguous_number(self):
        with tempfile.TemporaryDirectory() as directory:
            image = Image.new("RGB", (120, 80), (255, 255, 255))
            with patch("shooter_detector.subprocess.run") as run:
                run.return_value = SimpleNamespace(stdout="40\\n", returncode=0)
                result = read_ammunition(image, (0, 0, 100, 70), Path(directory) / "ocr.png")
        self.assertEqual(result, 40)

    def test_ammunition_ocr_rejects_multiple_numbers(self):
        with tempfile.TemporaryDirectory() as directory:
            image = Image.new("RGB", (120, 80), (255, 255, 255))
            with patch("shooter_detector.subprocess.run") as run:
                run.return_value = SimpleNamespace(stdout="40 20\\n", returncode=0)
                result = read_ammunition(image, (0, 0, 100, 70), Path(directory) / "ocr.png")
        self.assertIsNone(result)

    def test_ammunition_ocr_rejects_failed_tesseract_even_with_digits(self):
        with tempfile.TemporaryDirectory() as directory:
            image = Image.new("RGB", (120, 80), (255, 255, 255))
            with patch("shooter_detector.subprocess.run") as run:
                run.return_value = SimpleNamespace(stdout="40\\n", returncode=1)
                result = read_ammunition(image, (0, 0, 100, 70), Path(directory) / "ocr.png")
        self.assertIsNone(result)

    def test_brown_shooter_colour_is_distinguished_from_orange(self):
        self.assertEqual(identify_color((193, 126, 63))["name"], "brown")
        self.assertEqual(identify_color((230, 140, 50))["name"], "orange")


if __name__ == "__main__":
    unittest.main(verbosity=2)
