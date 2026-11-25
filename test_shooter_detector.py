import unittest
import hashlib
import json
import sys

import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from PIL import Image

from shooter_detector import (
    read_ammunition,
    read_ammunition_with_status,
    REF_W,
    REF_H,
    identify_color,
    scale_box,
    scale_point,
    validate_panel_image_size,
    verify_panel_crop,
    verify_panel_crop_bytes,

    extract_panel_crop,
    extract_panel_crop_bytes,

    load_user_confirmed_bonded_groups,
    assess_color_sample,
    load_user_confirmed_bonded_groups_with_provenance,
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
                 patch("shooter_detector.read_ammunition_with_status", return_value={"value": None, "status": "TESSERACT_UNAVAILABLE"}) as ocr, \
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
            self.assertIs(
                payload["observation_quality"]["ammunition_independently_verified"],
                False,
            )
            self.assertIs(
                payload["observation_quality"]["colour_independently_verified"],
                False,
            )
            self.assertIsNone(payload["bonding_config_sha256"])

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

    def test_panel_image_size_rejects_invalid_aspect_tolerance(self):
        for tolerance in (0, -0.1, 1.1, float("nan"), float("inf"), True, "0.02"):
            with self.subTest(tolerance=tolerance):
                with self.assertRaises(ValueError):
                    validate_panel_image_size(REF_W, REF_H, tolerance)

    def test_colour_sample_rejects_invalid_quality_thresholds(self):
        image = Image.new("RGB", (40, 40), (120, 120, 120))
        invalid_values = (
            (float("nan"), 32),
            (float("inf"), 32),
            (-1, 32),
            (442, 32),
            (24, float("nan")),
            (24, float("inf")),
            (24, -1),
            (24, 256),
            (True, 32),
            (24, "32"),
        )
        for minimum_contrast, maximum_mad in invalid_values:
            with self.subTest(
                minimum_contrast=minimum_contrast,
                maximum_mad=maximum_mad,
            ):
                with self.assertRaises(ValueError):
                    assess_color_sample(
                        image, 20, 20,
                        minimum_contrast=minimum_contrast,
                        maximum_mad=maximum_mad,
                    )

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

    def test_panel_crop_rejects_invalid_pixel_difference_tolerances(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.png"
            panel = root / "panel.png"
            Image.new("RGB", (20, 20), (10, 20, 30)).save(source)
            Image.new("RGB", (10, 10), (10, 20, 30)).save(panel)
            invalid_values = (
                -1, 256, float("nan"), float("inf"), True, "14",
            )
            for name in ("mean_tolerance", "percentile_tolerance"):
                for value in invalid_values:
                    with self.subTest(name=name, value=value):
                        kwargs = {name: value}
                        with self.assertRaisesRegex(ValueError, name):
                            verify_panel_crop(
                                source, panel, [0, 0, 20, 20], **kwargs
                            )

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
                run.return_value = SimpleNamespace(stdout="40\n", returncode=0)
                result = read_ammunition(image, (0, 0, 100, 70), Path(directory) / "ocr.png")
        self.assertEqual(result, 40)

    def test_ammunition_ocr_rejects_multiple_numbers(self):
        with tempfile.TemporaryDirectory() as directory:
            image = Image.new("RGB", (120, 80), (255, 255, 255))
            with patch("shooter_detector.subprocess.run") as run:
                run.return_value = SimpleNamespace(stdout="40 20\\n", returncode=0)
                result = read_ammunition(image, (0, 0, 100, 70), Path(directory) / "ocr.png")
        self.assertIsNone(result)

    def test_ammunition_ocr_rejects_digits_embedded_in_text(self):
        with tempfile.TemporaryDirectory() as directory:
            image = Image.new("RGB", (120, 80), (255, 255, 255))
            with patch("shooter_detector.subprocess.run") as run:
                run.return_value = SimpleNamespace(stdout="ammo: 40", returncode=0)
                result = read_ammunition(image, (0, 0, 100, 70), Path(directory) / "ocr.png")
        self.assertIsNone(result)

    def test_ammunition_ocr_rejects_excessively_long_number(self):
        with tempfile.TemporaryDirectory() as directory:
            image = Image.new("RGB", (120, 80), (255, 255, 255))
            with patch("shooter_detector.subprocess.run") as run:
                run.return_value = SimpleNamespace(stdout="9" * 5000, returncode=0)
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

    def test_ammunition_ocr_status_reports_exact_digit_success(self):
        with tempfile.TemporaryDirectory() as directory:
            image = Image.new("RGB", (120, 80), (255, 255, 255))
            with patch("shooter_detector.subprocess.run") as run:
                run.return_value = SimpleNamespace(stdout="40", returncode=0)
                result = read_ammunition_with_status(
                    image, (0, 0, 100, 70), Path(directory) / "ocr.png"
                )
        self.assertEqual(result, {"value": 40, "status": "PARSED_EXACT_DIGITS"})

    def test_ammunition_ocr_status_distinguishes_ambiguous_output(self):
        with tempfile.TemporaryDirectory() as directory:
            image = Image.new("RGB", (120, 80), (255, 255, 255))
            with patch("shooter_detector.subprocess.run") as run:
                run.return_value = SimpleNamespace(stdout="40 20", returncode=0)
                result = read_ammunition_with_status(
                    image, (0, 0, 100, 70), Path(directory) / "ocr.png"
                )
        self.assertIsNone(result["value"])
        self.assertEqual(result["status"], "AMBIGUOUS_OR_NON_INTEGER_OUTPUT")

    def test_ammunition_ocr_status_distinguishes_missing_tesseract(self):
        with tempfile.TemporaryDirectory() as directory:
            image = Image.new("RGB", (120, 80), (255, 255, 255))
            with patch("shooter_detector.subprocess.run", side_effect=FileNotFoundError("tesseract")):
                result = read_ammunition_with_status(
                    image, (0, 0, 100, 70), Path(directory) / "ocr.png"
                )
        self.assertEqual(result["status"], "TESSERACT_UNAVAILABLE")

    def test_ammunition_ocr_status_distinguishes_timeout(self):
        import subprocess
        with tempfile.TemporaryDirectory() as directory:
            image = Image.new("RGB", (120, 80), (255, 255, 255))
            with patch("shooter_detector.subprocess.run", side_effect=subprocess.TimeoutExpired("tesseract", 15)):
                result = read_ammunition_with_status(
                    image, (0, 0, 100, 70), Path(directory) / "ocr.png"
                )
        self.assertEqual(result["status"], "TESSERACT_TIMEOUT")

    def test_ammunition_ocr_status_distinguishes_nonzero_exit(self):
        with tempfile.TemporaryDirectory() as directory:
            image = Image.new("RGB", (120, 80), (255, 255, 255))
            with patch("shooter_detector.subprocess.run") as run:
                run.return_value = SimpleNamespace(stdout="40", returncode=2)
                result = read_ammunition_with_status(
                    image, (0, 0, 100, 70), Path(directory) / "ocr.png"
                )
        self.assertEqual(result["status"], "TESSERACT_NONZERO_EXIT")
        self.assertEqual(result["return_code"], 2)

    def test_detector_records_ocr_status_for_every_panel_slot(self):
        from shooter_detector import SHOOTERS, main
        image = Image.new("RGB", (REF_W, REF_H), (120, 120, 120))
        for shooter in SHOOTERS:
            x, y = shooter["sample"]
            image.paste(Image.new("RGB", (9, 9), (220, 40, 40)), (x - 4, y - 4))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            panel_path = root / "panel.jpg"
            output_path = root / "detection.json"
            image.save(panel_path)

            def sample_ocr(*args):
                return {"value": 25, "status": "PARSED_EXACT_DIGITS"}

            with patch("shooter_detector.IMAGE", panel_path), \
                 patch("shooter_detector.OUTPUT", output_path), \
                 patch("shooter_detector.read_ammunition_with_status", side_effect=sample_ocr):
                main()

            payload = json.loads(output_path.read_text())
        observations = payload["panel_slot_observations"]
        self.assertEqual(
            [item["ammunition_observation_status"] for item in observations[:4]],
            ["PARSED_EXACT_DIGITS"] * 4,
        )
        self.assertEqual(
            [item["ammunition_observation_status"] for item in observations[4:]],
            ["NOT_ATTEMPTED_UNVERIFIED_SLOT"] * 8,
        )
        self.assertEqual(
            payload["performance"]["ammunition_ocr_status_counts"],
            {"NOT_ATTEMPTED_UNVERIFIED_SLOT": 8, "PARSED_EXACT_DIGITS": 4},
        )
        self.assertTrue(all(item["ammo"] == 25 for item in payload["visible_shooters"]))
        self.assertTrue(all(
            item["ammo_observation_status"] == "PARSED_EXACT_DIGITS"
            for item in payload["visible_shooters"]
        ))

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

    def test_bonded_group_provenance_hashes_exact_config_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "groups.json"
            raw = b'{"verified_by_user": true, "bonded_groups": [["top_1", "top_2"]]}'
            path.write_bytes(raw)
            groups, source, digest = load_user_confirmed_bonded_groups_with_provenance(
                path, ["top_1", "top_2"]
            )
        self.assertEqual(groups, [["top_1", "top_2"]])
        self.assertEqual(source, "user_confirmed")
        self.assertEqual(digest, hashlib.sha256(raw).hexdigest())

    def test_missing_bonded_group_config_has_no_digest(self):
        with tempfile.TemporaryDirectory() as directory:
            groups, source, digest = load_user_confirmed_bonded_groups_with_provenance(
                Path(directory) / "missing.json", ["top_1", "top_2"]
            )
        self.assertEqual(groups, [])
        self.assertEqual(source, "not_configured")
        self.assertIsNone(digest)



    def test_byte_snapshot_extraction_and_verification_use_same_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = Image.new("RGB", (400, 300), (30, 80, 120))
            buffer = root / "source.png"
            source.save(buffer, format="PNG")
            source_bytes = buffer.read_bytes()
            output_path = root / "panel.jpg"
            extract_panel_crop_bytes(
                source_bytes, [20, 30, 327, 230], output_path
            )
            digest = verify_panel_crop_bytes(
                source_bytes, output_path, [20, 30, 327, 230]
            )
            self.assertEqual(digest, hashlib.sha256(source_bytes).hexdigest())

    def test_detector_hashes_and_crops_original_bytes_if_source_changes_after_read(self):
        from shooter_detector import SHOOTERS, main
        original_read_bytes = Path.read_bytes
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_path = root / "source.png"
            output_path = root / "detection.json"
            panel_path = root / "panel.jpg"
            original = Image.new("RGB", (400, 300), (30, 80, 120))
            original_bytes_buffer = root / "original.png"
            original.save(original_bytes_buffer, format="PNG")
            original_bytes = original_bytes_buffer.read_bytes()
            original.save(source_path)
            replacement = Image.new("RGB", (400, 300), (180, 20, 40))
            replacement.save(root / "replacement.png")
            replacement_bytes = (root / "replacement.png").read_bytes()
            changed = {"done": False}

            def read_then_replace(path):
                data = original_read_bytes(path)
                if Path(path) == source_path and not changed["done"]:
                    source_path.write_bytes(replacement_bytes)
                    changed["done"] = True
                return data

            with patch("shooter_detector.IMAGE", panel_path), \
                 patch("shooter_detector.OUTPUT", output_path), \
                 patch("shooter_detector.read_ammunition_with_status", return_value={"value": None, "status": "TESSERACT_UNAVAILABLE"}), \
                 patch.object(Path, "read_bytes", read_then_replace), \
                 patch.object(sys, "argv", [
                     "shooter_detector.py", "--source-screenshot",
                     str(source_path), "--panel-bounds",
                     "20", "30", "327", "230", "--extract-panel",
                     "--capture-session-id", "snapshot-test",
                     "--captured-at", "2026-11-24T12:00:00+01:00",
                     "--capture-config-sha256", "c" * 64,
                 ]):
                main()

            payload = json.loads(output_path.read_text())
            self.assertTrue(changed["done"])
            self.assertEqual(
                payload["capture_provenance"]["source_sha256"],
                hashlib.sha256(original_bytes).hexdigest(),
            )
            self.assertEqual(
                payload["capture_provenance"]["capture_config_sha256"],
                "c" * 64,
            )
            self.assertEqual(
                payload["capture_provenance"]["panel_bounds"],
                [20, 30, 327, 230],
            )
            self.assertNotEqual(
                payload["capture_provenance"]["source_sha256"],
                hashlib.sha256(replacement_bytes).hexdigest(),
            )
            with Image.open(panel_path) as panel:
                self.assertLess(panel.getpixel((10, 10))[0], 100)


if __name__ == "__main__":
    unittest.main(verbosity=2)
