import unittest
import io
from hashlib import sha256

from PIL import Image

from vision_calibration import (
    evaluate_dataset, validate_dataset, verify_source_image,
)


class VisionCalibrationTests(unittest.TestCase):
    def setUp(self):
        self.dataset = {
            "schema_version": 1,
            "labelled_by_user": True,
            "samples": [
                {"id": "cyan-1", "rgb": [104, 195, 233], "label": "cyan"},
                {"id": "red-1", "rgb": [230, 30, 30], "label": "red"},
                {"id": "red-labelled-orange", "rgb": [230, 30, 30], "label": "orange"},
                {"id": "white-1", "rgb": [245, 245, 245], "label": "white"},
            ],
        }

    def test_reports_accuracy_confusion_and_per_class_metrics(self):
        report = evaluate_dataset(self.dataset)
        self.assertEqual(report["sample_count"], 4)
        self.assertEqual(report["correct_count"], 3)
        self.assertEqual(report["accuracy"], 0.75)
        self.assertEqual(report["confusion_matrix"]["orange"]["red"], 1)
        self.assertEqual(report["per_class"]["red"]["precision"], 0.5)
        self.assertEqual(report["per_class"]["red"]["recall"], 1.0)
        self.assertEqual(report["per_class"]["orange"]["recall"], 0.0)

    def test_does_not_claim_independent_truth_or_gameplay_verification(self):
        report = evaluate_dataset(self.dataset)
        self.assertFalse(report["label_truth_independently_verified"])
        self.assertFalse(report["gameplay_verified"])
        self.assertFalse(report["game_taps_enabled"])
        self.assertIn("do not independently verify", report["interpretation"])

    def test_validates_user_labelled_dataset_gate(self):
        self.dataset["labelled_by_user"] = False
        with self.assertRaisesRegex(ValueError, "labelled_by_user"):
            validate_dataset(self.dataset)

    def test_rejects_duplicate_sample_ids(self):
        self.dataset["samples"].append(dict(self.dataset["samples"][0]))
        with self.assertRaisesRegex(ValueError, "Duplicate sample id"):
            validate_dataset(self.dataset)

    def test_rejects_boolean_and_out_of_range_rgb_channels(self):
        for rgb in ([True, 0, 0], [-1, 0, 0], [256, 0, 0], [0, 0]):
            with self.subTest(rgb=rgb):
                malformed = {
                    **self.dataset,
                    "samples": [{"id": "bad", "rgb": rgb, "label": "red"}],
                }
                with self.assertRaisesRegex(ValueError, "rgb must be"):
                    validate_dataset(malformed)

    def test_rejects_noncanonical_colour_label(self):
        for label in ("grey", "turquoise", "Red"):
            with self.subTest(label=label):
                malformed = {
                    **self.dataset,
                    "samples": [{"id": "bad-label", "rgb": [10, 20, 30], "label": label}],
                }
                with self.assertRaisesRegex(ValueError, "label must be one of"):
                    validate_dataset(malformed)

    def test_accepts_every_canonical_classifier_label(self):
        from screenshot_ingestor import COLOUR_LABELS

        samples = [
            {"id": f"label-{index}", "rgb": [20, 30, 40], "label": label}
            for index, label in enumerate(COLOUR_LABELS)
        ]
        validated = validate_dataset({
            "schema_version": 1,
            "labelled_by_user": True,
            "samples": samples,
        })
        self.assertEqual([sample["label"] for sample in validated], list(COLOUR_LABELS))

    def test_verifies_source_image_hash_and_dimensions_from_same_bytes(self):
        buffer = io.BytesIO()
        Image.new("RGB", (12, 8), (20, 30, 40)).save(buffer, format="PNG")
        image_bytes = buffer.getvalue()
        data = {
            **self.dataset,
            "source_sha256": sha256(image_bytes).hexdigest(),
            "image_size": [12, 8],
            "grid_size": [2, 2],
        }
        result = verify_source_image(data, image_bytes)
        self.assertEqual(result["sha256"], data["source_sha256"])
        self.assertTrue(result["dimensions_checked"])

    def test_supports_legacy_dataset_with_hash_but_no_recorded_dimensions(self):
        image_bytes = b"legacy screenshot bytes"
        data = {
            **self.dataset,
            "source_sha256": sha256(image_bytes).hexdigest(),
        }
        result = verify_source_image(data, image_bytes)
        self.assertEqual(result["sha256"], data["source_sha256"])
        self.assertFalse(result["dimensions_checked"])

    def test_rejects_hash_mismatch_before_attempting_image_decode(self):
        data = {
            **self.dataset,
            "source_sha256": "0" * 64,
            "image_size": [12, 8],
            "grid_size": [2, 2],
        }
        with self.assertRaisesRegex(ValueError, "SHA-256 does not match"):
            verify_source_image(data, b"not-an-image")
    def test_rejects_source_image_with_matching_hash_but_wrong_recorded_dimensions(self):
        buffer = io.BytesIO()
        Image.new("RGB", (12, 8), (20, 30, 40)).save(buffer, format="PNG")
        image_bytes = buffer.getvalue()
        data = {
            **self.dataset,
            "source_sha256": sha256(image_bytes).hexdigest(),
            "image_size": [8, 12],
            "grid_size": [2, 2],
        }
        with self.assertRaisesRegex(ValueError, "dimensions do not match"):
            verify_source_image(data, image_bytes)

    def test_rejects_unreadable_source_image_after_hash_matches(self):
        image_bytes = b"not-an-image"
        data = {
            **self.dataset,
            "source_sha256": sha256(image_bytes).hexdigest(),
            "image_size": [12, 8],
            "grid_size": [2, 2],
        }
        with self.assertRaisesRegex(ValueError, "not a readable image"):
            verify_source_image(data, image_bytes)

    def test_reports_source_image_provenance_from_template(self):

        data = {
            **self.dataset,
            "source_sha256": sha256(b"original screenshot").hexdigest(),
            "image_size": [1080, 2220],
            "grid_size": [2, 2],
            "samples": [
                {"id": "cell-1", "row": 0, "column": 0,
                 "rgb": [104, 195, 233], "label": "cyan"},
            ],
        }
        report = evaluate_dataset(data)
        self.assertEqual(
            report["source_provenance"]["source_sha256"],
            data["source_sha256"],
        )
        self.assertEqual(report["source_provenance"]["image_size"], [1080, 2220])
        self.assertFalse(report["source_provenance"]["source_image_hash_checked"])
        self.assertFalse(report["source_provenance"]["source_image_dimensions_checked"])

    def test_rejects_malformed_source_hash_and_grid_coordinates(self):
        malformed_hash = {**self.dataset, "source_sha256": "z" * 64}
        with self.assertRaisesRegex(ValueError, "source_sha256"):
            validate_dataset(malformed_hash)

        malformed_grid = {
            **self.dataset,
            "image_size": [1080, 2220],
            "grid_size": [2, 2],
            "samples": [
                {"id": "cell-1", "row": 2, "column": 0,
                 "rgb": [104, 195, 233], "label": "cyan"},
            ],
        }
        with self.assertRaisesRegex(ValueError, "row/column"):
            validate_dataset(malformed_grid)

    def test_rejects_grid_axis_above_dimension_limit(self):
        malformed = {
            **self.dataset,
            "image_size": [100, 100],
            "grid_size": [10001, 1],
            "samples": [
                {"id": "cell-1", "row": 0, "column": 0,
                 "rgb": [104, 195, 233], "label": "cyan"},
            ],
        }
        with self.assertRaisesRegex(ValueError, "dimensions must not exceed 10,000"):
            validate_dataset(malformed)

    def test_rejects_unreasonably_large_grid_dimensions(self):
        malformed = {
            **self.dataset,
            "image_size": [100, 100],
            "grid_size": [1001, 1000],
            "samples": [
                {"id": "cell-1", "row": 0, "column": 0,
                 "rgb": [104, 195, 233], "label": "cyan"},
            ],
        }
        with self.assertRaisesRegex(ValueError, "1,000,000 total cells"):
            validate_dataset(malformed)

    def test_rejects_duplicate_board_coordinates(self):
        data = {
            **self.dataset,
            "image_size": [100, 100],
            "grid_size": [4, 4],
            "samples": [
                {"id": "first", "row": 1, "column": 2,
                 "rgb": [104, 195, 233], "label": "cyan"},
                {"id": "duplicate-cell", "row": 1, "column": 2,
                 "rgb": [245, 245, 245], "label": "white"},
            ],
        }
        with self.assertRaisesRegex(ValueError, "Duplicate board coordinate"):
            validate_dataset(data)

    def test_requires_image_and_grid_dimensions_together(self):
        malformed = {**self.dataset, "image_size": [1080, 2220]}
        with self.assertRaisesRegex(ValueError, "supplied together"):
            validate_dataset(malformed)


    def test_flags_identical_rgb_values_with_conflicting_human_labels(self):
        data = {
            **self.dataset,
            "samples": [
                {"id": "same-red-a", "rgb": [230, 30, 30], "label": "red"},
                {"id": "same-red-b", "rgb": [230, 30, 30], "label": "orange"},
                {"id": "same-red-c", "rgb": [230, 30, 30], "label": "red"},
                {"id": "unique-cyan", "rgb": [104, 195, 233], "label": "cyan"},
            ],
        }
        coverage = evaluate_dataset(data)["coverage"]
        self.assertEqual(coverage["unique_rgb_count"], 2)
        self.assertEqual(coverage["repeated_rgb_group_count"], 1)
        self.assertEqual(coverage["conflicting_rgb_group_count"], 1)
        self.assertEqual(
            coverage["conflicting_rgb_groups"],
            [{
                "rgb": [230, 30, 30],
                "labels": ["orange", "red"],
                "sample_ids": ["same-red-a", "same-red-b", "same-red-c"],
            }],
        )

    def test_reports_repeated_rgb_without_false_conflict_when_labels_agree(self):
        data = {
            **self.dataset,
            "samples": [
                {"id": "cyan-a", "rgb": [104, 195, 233], "label": "cyan"},
                {"id": "cyan-b", "rgb": [104, 195, 233], "label": "cyan"},
            ],
        }
        coverage = evaluate_dataset(data)["coverage"]
        self.assertEqual(coverage["repeated_rgb_group_count"], 1)
        self.assertEqual(coverage["conflicting_rgb_group_count"], 0)
        self.assertEqual(coverage["conflicting_rgb_groups"], [])

    def test_reports_missing_classes_and_quadrant_coverage(self):
        data = {
            **self.dataset,
            "image_size": [100, 100],
            "grid_size": [4, 4],
            "samples": [
                {"id": "a", "row": 0, "column": 0,
                 "rgb": [104, 195, 233], "label": "cyan"},
                {"id": "b", "row": 3, "column": 3,
                 "rgb": [245, 245, 245], "label": "white"},
            ],
        }
        coverage = evaluate_dataset(data)["coverage"]
        self.assertEqual(coverage["class_sample_counts"]["cyan"], 1)
        self.assertEqual(coverage["class_sample_counts"]["white"], 1)
        self.assertIn("red", coverage["missing_classes"])
        self.assertTrue(coverage["spatial_coverage_available"])
        self.assertEqual(coverage["spatial_regions"]["top_left"]["sample_count"], 1)
        self.assertEqual(coverage["spatial_regions"]["bottom_right"]["sample_count"], 1)
        self.assertEqual(coverage["empty_spatial_regions"], ["top_right", "bottom_left"])
        self.assertFalse(coverage["coverage_adequacy_assessed"])
        self.assertEqual(coverage["board_cell_coverage"]["sampled_cell_count"], 2)
        self.assertEqual(coverage["board_cell_coverage"]["total_board_cell_count"], 16)
        self.assertEqual(coverage["board_cell_coverage"]["unsampled_cell_count"], 14)
        self.assertEqual(coverage["board_cell_coverage"]["sample_coverage_fraction"], 0.125)
        self.assertEqual(coverage["board_cell_coverage"]["rows_without_samples"], [1, 2])
        self.assertEqual(coverage["board_cell_coverage"]["columns_without_samples"], [1, 2])
        self.assertEqual(coverage["board_cell_coverage"]["row_sample_counts"], {"0": 1, "3": 1})
        self.assertEqual(coverage["board_cell_coverage"]["column_sample_counts"], {"0": 1, "3": 1})

    def test_reports_class_counts_without_claiming_spatial_coverage(self):
        coverage = evaluate_dataset(self.dataset)["coverage"]
        self.assertFalse(coverage["spatial_coverage_available"])
        self.assertIsNone(coverage["spatial_regions"])
        self.assertFalse(coverage["coverage_adequacy_assessed"])

    def test_rejects_empty_or_malformed_datasets(self):
        for malformed in (None, [], {}, {
            "schema_version": 1, "labelled_by_user": True, "samples": []
        }):
            with self.subTest(malformed=malformed):
                with self.assertRaises(ValueError):
                    validate_dataset(malformed)


if __name__ == "__main__":
    unittest.main(verbosity=2)
