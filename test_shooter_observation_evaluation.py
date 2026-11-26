import copy
import unittest

from prepare_shooter_labels import build_template
from shooter_observation_evaluation import (
    evaluate_dataset,
    validate_dataset,
    verify_source_artifacts,
)
from test_prepare_shooter_labels import fixture_artifacts


def labelled_fixture():
    detection, detection_bytes, screenshot_bytes = fixture_artifacts()
    dataset = build_template(detection, detection_bytes, screenshot_bytes)
    dataset["labelled_by_user"] = True
    for sample in dataset["samples"]:
        detector = sample["detector"]
        row, column = detector["row"], detector["column"]
        sample["review_status"] = "confirmed"
        if row == 1:
            sample["human"] = {
                "visibility": "visible",
                "row": row,
                "column": column,
                "colour": "red",
                "ammunition_readable": True,
                "ammunition": detector["ammunition"],
            }
        elif row == 2:
            sample["human"] = {
                "visibility": "unrevealed",
                "row": row,
                "column": column,
                "colour": "",
                "ammunition_readable": False,
                "ammunition": None,
            }
        else:
            sample["human"] = {
                "visibility": "partially_occluded",
                "row": row,
                "column": column,
                "colour": "",
                "ammunition_readable": False,
                "ammunition": None,
            }
    return dataset, detection_bytes, screenshot_bytes


class ShooterObservationEvaluationTests(unittest.TestCase):
    def test_reports_visibility_position_colour_and_ammunition_metrics(self):
        dataset, _, _ = labelled_fixture()
        # Simulate three independently reviewed disagreements.
        dataset["samples"][0]["human"]["row"] = 2
        dataset["samples"][1]["human"]["colour"] = "cyan"
        dataset["samples"][2]["human"]["ammunition"] += 1
        dataset["samples"][11]["human"]["visibility"] = "empty"

        report = evaluate_dataset(dataset)
        metrics = report["metrics"]
        self.assertEqual(report["confirmed_sample_count"], 12)
        self.assertEqual(metrics["visibility"]["support"], 12)
        self.assertEqual(metrics["visibility"]["accuracy"], round(11 / 12, 6))
        self.assertAlmostEqual(metrics["visibility"]["macro_f1"], 0.714286, places=5)
        self.assertEqual(metrics["visibility"]["per_class"]["visible"]["support"], 4)
        self.assertEqual(metrics["visibility"]["per_class"]["visible"]["recall"], 1.0)
        self.assertEqual(metrics["slot_position_alignment"]["support"], 12)
        self.assertEqual(metrics["slot_position_alignment"]["accuracy"], round(11 / 12, 6))
        self.assertEqual(metrics["colour"]["support"], 4)
        self.assertEqual(metrics["colour"]["accuracy"], 0.75)
        self.assertEqual(metrics["ammunition"]["support"], 4)
        self.assertEqual(metrics["ammunition"]["exact_match_count"], 3)
        self.assertEqual(metrics["ammunition"]["exact_match_accuracy"], 0.75)
        coverage = report["coverage_profile"]
        self.assertEqual(
            coverage["panel_positions_with_confirmed_labels"], 12
        )
        self.assertEqual(
            coverage["human_visibility_class_support"],
            {
                "visible": 4, "unrevealed": 4,
                "partially_occluded": 3, "empty": 1,
            },
        )
        self.assertEqual(coverage["human_visible_colour_support"]["red"], 3)
        self.assertEqual(coverage["human_visible_colour_support"]["cyan"], 1)
        self.assertEqual(
            coverage["human_legible_ammunition_value_support"],
            [
                {"value": 11, "count": 1},
                {"value": 12, "count": 1},
                {"value": 14, "count": 2},
            ],
        )
        self.assertEqual(report["review_follow_up"]["panel_review_targets"], [])
        self.assertEqual(
            report["review_follow_up"][
                "visibility_classes_with_zero_confirmed_support"
            ],
            [],
        )
        self.assertEqual(
            report["review_follow_up"][
                "visible_colour_classes_with_zero_confirmed_support"
            ],
            [
                "black", "white", "gray", "brown", "orange", "yellow",
                "green", "blue", "purple", "magenta",
            ],
        )
        self.assertFalse(coverage["coverage_adequacy_assessed"])
        self.assertFalse(report["review_follow_up"]["coverage_adequacy_assessed"])
        self.assertFalse(report["label_truth_independently_verified"])
        self.assertFalse(report["colour_independently_verified"])
        self.assertFalse(report["ammunition_independently_verified"])
        self.assertFalse(report["gameplay_verified"])
        self.assertFalse(report["game_taps_enabled"])

    def test_ambiguous_samples_are_excluded_from_scored_metrics(self):
        dataset, _, _ = labelled_fixture()
        dataset["samples"][0]["review_status"] = "ambiguous"
        dataset["samples"][0]["human"] = {
            "visibility": "", "row": None, "column": None,
            "colour": "", "ammunition_readable": None, "ammunition": None,
        }
        report = evaluate_dataset(dataset)
        self.assertEqual(report["ambiguous_sample_count"], 1)
        self.assertEqual(report["confirmed_sample_count"], 11)
        self.assertEqual(report["metrics"]["visibility"]["support"], 11)
        target = report["review_follow_up"]["panel_review_targets"][0]
        self.assertEqual(target, {
            "position": "r1c1",
            "status": "ambiguous_only",
            "confirmed_count": 0,
            "ambiguous_count": 1,
        })
        self.assertEqual(
            report["coverage_profile"][
                "detector_panel_position_review_counts"
            ]["r1c1"],
            {"confirmed": 0, "ambiguous": 1},
        )
        self.assertFalse(report["review_follow_up"]["coverage_adequacy_assessed"])

    def test_rejects_dataset_without_explicit_user_review(self):
        dataset, _, _ = labelled_fixture()
        dataset["labelled_by_user"] = False
        with self.assertRaisesRegex(ValueError, "labelled_by_user"):
            validate_dataset(dataset)

    def test_rejects_invalid_capture_timestamp(self):
        dataset, _, _ = labelled_fixture()
        dataset["capture_provenance"]["captured_at"] = "not-a-timestamp"
        with self.assertRaisesRegex(ValueError, "captured_at is invalid"):
            validate_dataset(dataset)

    def test_rejects_capture_timestamp_without_timezone(self):
        dataset, _, _ = labelled_fixture()
        dataset["capture_provenance"]["captured_at"] = "2026-11-26T12:00:00"
        with self.assertRaisesRegex(ValueError, "must include a UTC offset"):
            validate_dataset(dataset)

    def test_rejects_any_sample_left_unreviewed(self):
        dataset, _, _ = labelled_fixture()
        dataset["samples"][0]["review_status"] = "not_reviewed"
        with self.assertRaisesRegex(ValueError, "confirmed or ambiguous"):
            validate_dataset(dataset)

    def test_rejects_boolean_human_ammunition(self):
        dataset, _, _ = labelled_fixture()
        dataset["samples"][0]["human"]["ammunition"] = True
        with self.assertRaisesRegex(ValueError, "non-negative integer"):
            validate_dataset(dataset)

    def test_rejects_noncanonical_human_colour(self):
        dataset, _, _ = labelled_fixture()
        dataset["samples"][0]["human"]["colour"] = "turquoise"
        with self.assertRaisesRegex(ValueError, "canonical human colour"):
            validate_dataset(dataset)

    def test_rejects_invalid_human_visibility(self):
        dataset, _, _ = labelled_fixture()
        dataset["samples"][4]["human"]["visibility"] = "maybe"
        with self.assertRaisesRegex(ValueError, "human visibility"):
            validate_dataset(dataset)

    def test_source_artifact_verification_checks_both_exact_hashes(self):
        dataset, detection_bytes, screenshot_bytes = labelled_fixture()
        result = verify_source_artifacts(dataset, detection_bytes, screenshot_bytes)
        self.assertEqual(
            result["source_detection_sha256"],
            dataset["source_detection_sha256"],
        )
        self.assertEqual(
            result["source_screenshot_sha256"],
            dataset["source_screenshot_sha256"],
        )
        self.assertTrue(result["screenshot_dimensions_checked"])

    def test_rejects_different_source_screenshot(self):
        dataset, detection_bytes, screenshot_bytes = labelled_fixture()
        with self.assertRaisesRegex(ValueError, "Source screenshot SHA-256"):
            verify_source_artifacts(dataset, detection_bytes, screenshot_bytes + b"x")

    def test_rejects_different_source_detector_json(self):
        dataset, detection_bytes, screenshot_bytes = labelled_fixture()
        with self.assertRaisesRegex(ValueError, "Source detector SHA-256"):
            verify_source_artifacts(dataset, detection_bytes + b" ", screenshot_bytes)

    def test_rejects_edited_detector_snapshot_inside_labelled_dataset(self):
        dataset, detection_bytes, screenshot_bytes = labelled_fixture()
        dataset["samples"][0]["detector"]["colour"] = "blue"
        with self.assertRaisesRegex(ValueError, "detector snapshot"):
            verify_source_artifacts(dataset, detection_bytes, screenshot_bytes)

    def test_reports_ammunition_ocr_status_counts_and_per_sample_status(self):
        dataset, _, _ = labelled_fixture()
        dataset["samples"][0]["detector"]["ammunition_observation_status"] = (
            "TESSERACT_TIMEOUT"
        )
        dataset["samples"][0]["detector"]["ammunition"] = None
        report = evaluate_dataset(dataset)
        self.assertEqual(
            report["review_coverage"]["visible_ammunition_ocr_status_counts"][
                "TESSERACT_TIMEOUT"
            ],
            1,
        )
        self.assertEqual(
            report["sample_results"][0]["detected_ammunition_status"],
            "TESSERACT_TIMEOUT",
        )

    def test_rejects_ammunition_value_with_inconsistent_ocr_status(self):
        dataset, _, _ = labelled_fixture()
        dataset["samples"][0]["detector"]["ammunition_observation_status"] = (
            "TESSERACT_TIMEOUT"
        )
        with self.assertRaisesRegex(ValueError, "non-success OCR status"):
            validate_dataset(dataset)

    def test_evaluation_does_not_claim_source_artifacts_checked_without_verifier(self):
        dataset, _, _ = labelled_fixture()
        report = evaluate_dataset(dataset)
        self.assertFalse(report["source_provenance"]["source_detection_hash_checked"])
        self.assertFalse(report["source_provenance"]["source_screenshot_hash_checked"])
        self.assertFalse(
            report["source_provenance"]["source_screenshot_dimensions_checked"]
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
