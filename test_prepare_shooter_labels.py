import hashlib
import io
import json
import unittest

from PIL import Image

from prepare_shooter_labels import build_template


def fixture_artifacts():
    image_buffer = io.BytesIO()
    Image.new("RGB", (1080, 2220), (12, 34, 56)).save(image_buffer, format="PNG")
    screenshot_bytes = image_buffer.getvalue()
    screenshot_hash = hashlib.sha256(screenshot_bytes).hexdigest()

    slots = []
    observations = []
    for row in range(1, 4):
        for column in range(1, 5):
            if row == 1:
                slot_id, slot_status, observation_status = (
                    f"top_{column}", "readable", "readable_candidate"
                )
            elif row == 2:
                slot_id, slot_status, observation_status = (
                    f"question_{column}", "unrevealed", "unrevealed_candidate"
                )
            else:
                slot_id, slot_status, observation_status = (
                    f"lower_{column}", "partially_occluded",
                    "partially_occluded_candidate"
                )
            x, y = column * 180, row * 280
            slots.append({
                "id": slot_id,
                "row": row,
                "column": column,
                "center": [x, y],
                "status": slot_status,
                "selectable_candidate": False,
            })
            observations.append({
                "id": slot_id,
                "row": row,
                "column": column,
                "color_observation": {
                    "name": "red",
                    "rgb": [200, 40, 40],
                    "hex": "#C82828",
                    "hsv": [0.0, 80.0, 78.4],
                },
                "sample_quality": {"status": "DISTINCT_SAMPLE"},
                "ammunition_observation": 10 + column if row == 1 else None,
                "screen_center": [x, y],
                "screen_box": [x - 30, y - 30, x + 30, y + 30],
                "screen_sample": [x, y],
                "status": observation_status,
                "verified": False,
                "selectable_candidate": False,
            })

    detection = {
        "capture_provenance": {
            "verified": True,
            "source_sha256": screenshot_hash,
            "capture_config_sha256": "b" * 64,
            "capture_session_id": "session-abc",
            "captured_at": "2026-11-25T12:00:00+00:00",
            "panel_bounds": [20, 30, 820, 550],
        },
        "image_dimensions": [1536, 999],
        "panel_layout": {"rows": 3, "columns": 4, "slot_count": 12},
        "panel_slots": slots,
        "panel_slot_observations": observations,
        "observation_quality": {
            "colour_method": "fixed_panel_sample_hsv_thresholds",
            "colour_independently_verified": False,
            "ammunition_method": "tesseract_exact_digit_ocr",
            "ammunition_independently_verified": False,
            "slot_mapping_method": "fixed_panel_calibration",
            "slot_mapping_independently_verified": False,
        },
    }
    detection_bytes = json.dumps(
        detection, separators=(",", ":")
    ).encode("utf-8")
    return detection, detection_bytes, screenshot_bytes


class PrepareShooterLabelsTests(unittest.TestCase):
    def test_template_keeps_human_labels_blank_and_binds_both_sources(self):
        detection, detection_bytes, screenshot_bytes = fixture_artifacts()
        template = build_template(detection, detection_bytes, screenshot_bytes)

        self.assertFalse(template["labelled_by_user"])
        self.assertEqual(len(template["samples"]), 12)
        self.assertEqual(
            template["source_detection_sha256"],
            hashlib.sha256(detection_bytes).hexdigest(),
        )
        self.assertEqual(
            template["source_screenshot_sha256"],
            hashlib.sha256(screenshot_bytes).hexdigest(),
        )
        for sample in template["samples"]:
            self.assertEqual(sample["review_status"], "not_reviewed")
            self.assertEqual(sample["human"]["visibility"], "")
            self.assertIsNone(sample["human"]["ammunition"])
            self.assertEqual(sample["detector"]["colour"], "red")

    def test_template_rejects_screenshot_not_used_by_capture(self):
        detection, detection_bytes, _ = fixture_artifacts()
        other = io.BytesIO()
        Image.new("RGB", (1080, 2220), (90, 80, 70)).save(other, format="PNG")
        with self.assertRaisesRegex(ValueError, "SHA-256 does not match"):
            build_template(detection, detection_bytes, other.getvalue())

    def test_template_rejects_panel_bounds_outside_source_screenshot(self):
        detection, _, screenshot_bytes = fixture_artifacts()
        detection["capture_provenance"]["panel_bounds"] = [20, 30, 1200, 550]
        raw = json.dumps(detection).encode()
        with self.assertRaisesRegex(ValueError, "outside the source screenshot"):
            build_template(detection, raw, screenshot_bytes)

    def test_template_rejects_panel_bounds_with_wrong_aspect_ratio(self):
        detection, _, screenshot_bytes = fixture_artifacts()
        detection["capture_provenance"]["panel_bounds"] = [20, 30, 820, 620]
        raw = json.dumps(detection).encode()
        with self.assertRaisesRegex(ValueError, "aspect ratio"):
            build_template(detection, raw, screenshot_bytes)

    def test_template_rejects_unverified_capture_provenance(self):
        detection, detection_bytes, screenshot_bytes = fixture_artifacts()
        detection["capture_provenance"]["verified"] = False
        detection_bytes = json.dumps(detection).encode()
        with self.assertRaisesRegex(ValueError, "explicitly verified"):
            build_template(detection, detection_bytes, screenshot_bytes)

    def test_template_rejects_detection_object_that_differs_from_exact_bytes(self):
        detection, detection_bytes, screenshot_bytes = fixture_artifacts()
        changed = dict(detection)
        changed["panel_slot_observations"] = [dict(item) for item in detection["panel_slot_observations"]]
        changed["panel_slot_observations"][0]["color_observation"] = dict(
            detection["panel_slot_observations"][0]["color_observation"],
            name="blue",
        )
        with self.assertRaisesRegex(ValueError, "does not match"):
            build_template(changed, detection_bytes, screenshot_bytes)

    def test_template_rejects_duplicate_slot_positions(self):
        detection, _, screenshot_bytes = fixture_artifacts()
        detection["panel_slots"][1]["row"] = 1
        detection["panel_slots"][1]["column"] = 1
        detection["panel_slots"][1]["id"] = "duplicate-position"
        detection["panel_slot_observations"][1]["id"] = "duplicate-position"
        detection["panel_slot_observations"][1]["row"] = 1
        detection["panel_slot_observations"][1]["column"] = 1
        raw = json.dumps(detection).encode()
        with self.assertRaisesRegex(ValueError, "Duplicate panel slot position"):
            build_template(detection, raw, screenshot_bytes)

    def test_template_rejects_missing_panel_observation(self):
        detection, _, screenshot_bytes = fixture_artifacts()
        detection["panel_slot_observations"].pop()
        raw = json.dumps(detection).encode()
        with self.assertRaisesRegex(ValueError, "exactly panel_layout.slot_count"):
            build_template(detection, raw, screenshot_bytes)

    def test_template_rejects_unknown_detector_colour(self):
        detection, _, screenshot_bytes = fixture_artifacts()
        detection["panel_slot_observations"][0]["color_observation"]["name"] = "turquoise"
        raw = json.dumps(detection).encode()
        with self.assertRaisesRegex(ValueError, "invalid detected colour"):
            build_template(detection, raw, screenshot_bytes)

    def test_template_rejects_screen_box_outside_panel_image(self):
        detection, _, screenshot_bytes = fixture_artifacts()
        detection["panel_slot_observations"][0]["screen_box"] = [1, 1, 1600, 20]
        raw = json.dumps(detection).encode()
        with self.assertRaisesRegex(ValueError, "outside panel dimensions"):
            build_template(detection, raw, screenshot_bytes)


if __name__ == "__main__":
    unittest.main(verbosity=2)
