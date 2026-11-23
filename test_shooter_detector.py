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
    load_user_confirmed_bonded_groups,
    assess_color_sample,
)


class ShooterDetectorCalibrationTests(unittest.TestCase):

    def test_detector_observes_all_twelve_slots_without_unlocking_lower_rows(self):
        from shooter_detector import SHOOTERS, main
        import json
        import sys
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            panel_path = root / "panel.jpg"
            output_path = root / "detection.json"
            image = Image.new("RGB", (REF_W, REF_H), (35, 35, 35))
            for offset in (0, 300, 600):
                for shooter in SHOOTERS:
                    x, y = shooter["sample"]
                    image.paste(Image.new("RGB", (9, 9), (220, 40, 40)),
                                (x - 4, y + offset - 4))
            image.save(panel_path)
            with patch("shooter_detector.IMAGE", panel_path), \
                 patch("shooter_detector.OUTPUT", output_path), \
                 patch("shooter_detector.read_ammunition", return_value=None) as ocr, \
                 patch.object(sys, "argv", ["shooter_detector.py"]):
                main()
                self.assertEqual(ocr.call_count, 4)
            payload = json.loads(output_path.read_text())
            observations = payload["panel_slot_observations"]
            self.assertEqual(len(observations), 12)
            self.assertEqual([x["row"] for x in observations],
                             [1] * 4 + [2] * 4 + [3] * 4)
            self.assertTrue(all(not x["selectable_candidate"] for x in observations))
            self.assertEqual(len(payload["visible_shooters"]), 4)
            self.assertEqual(payload["performance"]["ammunition_ocr_calls"], 4)
            self.assertEqual(payload["performance"]["panel_slots_observed"], 12)
            self.assertGreaterEqual(payload["performance"]["shooter_detection_seconds"], 0)

    def test_sample_quality_detects_distinct_colour_patch(self):
        image = Image.new("RGB", (40, 40), (35, 35, 35))
        image.paste(Image.new("RGB", (9, 9), (220, 40, 40)), (16, 16))
        result = assess_color_sample(image, 20, 20)
        self.assertEqual(result["status"], "DISTINCT_SAMPLE")
        self.assertGreaterEqual(result["local_contrast"], 24)
        self.assertEqual(result["median_absolute_deviation"], 0)

    def test_sample_quality_rejects_uniform_background(self):
        image = Image.new("RGB", (40, 40), (35, 35, 35))
        result = assess_color_sample(image, 20, 20)
        self.assertEqual(result["status"], "LOW_CONFIDENCE_SAMPLE")
        self.assertEqual(result["local_contrast"], 0)

    def test_sample_quality_rejects_sample_near_image_edge(self):
        image = Image.new("RGB", (40, 40), (35, 35, 35))
        with self.assertRaisesRegex(ValueError, "outside"):
            assess_color_sample(image, 5, 20)

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

    def test_full_panel_inventory_includes_all_three_rows(self):
        from shooter_detector import build_panel_slot_inventory
        slots = build_panel_slot_inventory(REF_W, REF_H)
        self.assertEqual(len(slots), 12)
        self.assertEqual(
            [(slot["row"], slot["column"]) for slot in slots],
            [(row, column) for row in range(1, 4) for column in range(1, 5)],
        )
        self.assertEqual(
            [slot["status"] for slot in slots[:4]],
            ["readable"] * 4,
        )
        self.assertEqual(
            [slot["status"] for slot in slots[4:8]],
            ["unrevealed"] * 4,
        )
        self.assertEqual(
            [slot["status"] for slot in slots[8:]],
            ["partially_occluded"] * 4,
        )
        self.assertTrue(all(not slot["selectable_candidate"] for slot in slots))

    def test_panel_inventory_scales_slot_centres(self):
        from shooter_detector import build_panel_slot_inventory
        slots = build_panel_slot_inventory(REF_W // 2, REF_H // 2)
        self.assertEqual(slots[0]["center"], [165, 137])
        self.assertEqual(slots[4]["center"], [165, 287])

    def test_panel_inventory_rejects_invalid_dimensions(self):
        from shooter_detector import build_panel_slot_inventory
        for dimensions in [(0, 999), (1536, 0), (True, 999), (1536.0, 999)]:
            with self.subTest(dimensions=dimensions):
                with self.assertRaises(ValueError):
                    build_panel_slot_inventory(*dimensions)

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

    def test_ammunition_ocr_handles_missing_tesseract(self):
        with tempfile.TemporaryDirectory() as directory:
            image = Image.new("RGB", (120, 80), (255, 255, 255))
            with patch("shooter_detector.subprocess.run",
                       side_effect=FileNotFoundError("tesseract")):
                result = read_ammunition(image, (0, 0, 100, 70), Path(directory) / "ocr.png")
        self.assertIsNone(result)

    def test_ammunition_ocr_handles_tesseract_timeout(self):
        import subprocess
        with tempfile.TemporaryDirectory() as directory:
            image = Image.new("RGB", (120, 80), (255, 255, 255))
            with patch("shooter_detector.subprocess.run",
                       side_effect=subprocess.TimeoutExpired("tesseract", 15)):
                result = read_ammunition(image, (0, 0, 100, 70), Path(directory) / "ocr.png")
        self.assertIsNone(result)

    def test_brown_shooter_colour_is_distinguished_from_orange(self):
        self.assertEqual(identify_color((193, 126, 63))["name"], "brown")
        self.assertEqual(identify_color((230, 140, 50))["name"], "orange")

    def test_bonded_groups_are_empty_without_explicit_user_config(self):
        with tempfile.TemporaryDirectory() as directory:
            groups, source = load_user_confirmed_bonded_groups(
                Path(directory) / "missing.json",
                ["top_1", "top_2", "top_3", "top_4"],
            )
        self.assertEqual(groups, [])
        self.assertEqual(source, "not_configured")

    def test_unconfirmed_bonded_group_config_is_ignored(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "groups.json"
            path.write_text('{"verified_by_user": false, "bonded_groups": [["top_1", "top_2"]]}')
            groups, source = load_user_confirmed_bonded_groups(
                path, ["top_1", "top_2"]
            )
        self.assertEqual(groups, [])
        self.assertEqual(source, "not_user_confirmed")

    def test_explicitly_confirmed_bonded_groups_are_loaded(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "groups.json"
            path.write_text('{"verified_by_user": true, "bonded_groups": [["top_1", "top_2"]]}')
            groups, source = load_user_confirmed_bonded_groups(
                path, ["top_1", "top_2"]
            )
        self.assertEqual(groups, [["top_1", "top_2"]])
        self.assertEqual(source, "user_confirmed")

    def test_confirmed_bonded_groups_reject_unknown_ids(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "groups.json"
            path.write_text('{"verified_by_user": true, "bonded_groups": [["top_1", "missing"]]}')
            with self.assertRaisesRegex(ValueError, "unknown shooters"):
                load_user_confirmed_bonded_groups(path, ["top_1", "top_2"])

    def test_confirmed_bonded_groups_reject_overlapping_membership(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "groups.json"
            path.write_text('{"verified_by_user": true, "bonded_groups": [["A", "B"], ["A", "C"]]}')
            with self.assertRaisesRegex(ValueError, "multiple bonded groups"):
                load_user_confirmed_bonded_groups(path, ["A", "B", "C"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
