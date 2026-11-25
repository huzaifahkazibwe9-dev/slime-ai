import copy
import hashlib
import json
import unittest

from shooter_review_agreement import (
    _agreement_summary,
    evaluate_review_agreement,
)
from test_shooter_observation_evaluation import labelled_fixture


class ShooterReviewAgreementTests(unittest.TestCase):
    def test_identical_source_bound_reviews_agree_on_all_fields(self):
        dataset_a, detection_bytes, screenshot_bytes = labelled_fixture()
        dataset_b = copy.deepcopy(dataset_a)

        report = evaluate_review_agreement(
            dataset_a,
            dataset_b,
            "reviewer-a",
            "reviewer-b",
            detection_bytes,
            screenshot_bytes,
        )

        self.assertEqual(report["sample_count"], 12)
        self.assertEqual(report["both_confirmed_sample_count"], 12)
        self.assertEqual(report["both_ambiguous_sample_count"], 0)
        self.assertEqual(report["one_or_both_ambiguous_sample_count"], 0)
        self.assertEqual(report["disagreement_count"], 0)
        self.assertEqual(len(report["per_slot_agreement"]), 12)
        self.assertEqual(
            report["per_slot_agreement"]["top_1"]["field_agreement"]["colour"]["agreement_rate"],
            1.0,
        )
        self.assertEqual(report["field_agreement"]["review_status"]["agreement_rate"], 1.0)
        self.assertEqual(report["field_agreement"]["visibility"]["agreement_rate"], 1.0)
        self.assertEqual(report["field_agreement"]["position"]["agreement_rate"], 1.0)
        self.assertEqual(report["field_agreement"]["colour"]["agreement_rate"], 1.0)
        self.assertEqual(
            report["field_agreement"]["ammunition_readability"]["agreement_rate"],
            1.0,
        )
        self.assertEqual(
            report["field_agreement"]["ammunition_exact_value"]["agreement_rate"],
            1.0,
        )
        self.assertEqual(
            report["field_agreement"]["ammunition_exact_value"]["cohen_kappa"],
            1.0,
        )
        self.assertTrue(
            report["source_provenance"][
                "source_artifacts_verified_for_both_reviews"
            ]
        )
        self.assertTrue(report["source_provenance"]["source_verification_consistent"])
        self.assertFalse(report["reviewer_independence_verified"])
        self.assertFalse(report["label_truth_independently_verified"])
        self.assertFalse(report["gameplay_verified"])
        self.assertFalse(report["game_taps_enabled"])

    def test_reports_field_disagreements_and_excludes_ineligible_labels(self):
        dataset_a, detection_bytes, screenshot_bytes = labelled_fixture()
        dataset_b = copy.deepcopy(dataset_a)

        dataset_b["samples"][0]["human"]["colour"] = "cyan"

        dataset_b["samples"][1]["human"].update({
            "visibility": "empty",
            "colour": "",
            "ammunition_readable": False,
            "ammunition": None,
        })

        dataset_b["samples"][2]["human"]["ammunition"] += 1

        dataset_b["samples"][3]["review_status"] = "ambiguous"
        dataset_b["samples"][3]["human"] = {
            "visibility": "", "row": None, "column": None,
            "colour": "", "ammunition_readable": None, "ammunition": None,
        }

        report = evaluate_review_agreement(
            dataset_a,
            dataset_b,
            "reviewer-a",
            "reviewer-b",
            detection_bytes,
            screenshot_bytes,
        )

        self.assertEqual(report["both_confirmed_sample_count"], 11)
        self.assertEqual(report["one_or_both_ambiguous_sample_count"], 1)
        self.assertEqual(report["field_agreement"]["review_status"]["support"], 12)
        self.assertEqual(report["field_agreement"]["review_status"]["agreement_rate"], round(11 / 12, 6))
        self.assertEqual(report["field_agreement"]["visibility"]["support"], 11)
        self.assertEqual(report["field_agreement"]["visibility"]["agreement_rate"], round(10 / 11, 6))
        self.assertEqual(report["field_agreement"]["position"]["support"], 11)
        self.assertEqual(report["field_agreement"]["colour"]["support"], 2)
        self.assertEqual(report["field_agreement"]["colour"]["agreement_rate"], 0.5)
        self.assertEqual(report["field_agreement"]["ammunition_readability"]["support"], 2)
        self.assertEqual(report["field_agreement"]["ammunition_exact_value"]["support"], 2)
        self.assertEqual(report["field_agreement"]["ammunition_exact_value"]["agreement_rate"], 0.5)
        disagreements = {
            item["sample_id"]: {
                entry["field"] for entry in item["disagreements"]
            }
            for item in report["disagreements"]
        }
        self.assertEqual(disagreements["top_1"], {"colour"})
        self.assertEqual(disagreements["top_2"], {"visibility"})
        self.assertEqual(disagreements["top_3"], {"ammunition_exact_value"})
        self.assertEqual(disagreements["top_4"], {"review_status"})
        self.assertEqual(
            report["per_slot_agreement"]["top_1"]["field_agreement"]["colour"]["agreement_rate"],
            0.0,
        )
        self.assertEqual(
            report["per_slot_agreement"]["top_2"]["field_agreement"]["colour"]["support"],
            0,
        )
        self.assertEqual(
            report["per_slot_agreement"]["top_4"]["field_agreement"]["review_status"]["agreement_rate"],
            0.0,
        )

    def test_fingerprints_exact_reviewer_dataset_file_bytes(self):
        dataset_a, detection_bytes, screenshot_bytes = labelled_fixture()
        dataset_b = copy.deepcopy(dataset_a)
        raw_a = json.dumps(dataset_a, indent=2).encode("utf-8")
        raw_b = json.dumps(dataset_b, separators=(",", ":")).encode("utf-8")
        report = evaluate_review_agreement(
            dataset_a,
            dataset_b,
            "reviewer-a",
            "reviewer-b",
            detection_bytes,
            screenshot_bytes,
            raw_a,
            raw_b,
        )
        provenance = report["review_dataset_provenance"]
        self.assertEqual(
            provenance["reviewer_a_dataset_sha256"],
            hashlib.sha256(raw_a).hexdigest(),
        )
        self.assertEqual(
            provenance["reviewer_b_dataset_sha256"],
            hashlib.sha256(raw_b).hexdigest(),
        )
        self.assertEqual(provenance["reviewer_a_hash_mode"], "raw_file_bytes")
        self.assertEqual(provenance["reviewer_b_hash_mode"], "raw_file_bytes")
        self.assertNotEqual(
            provenance["reviewer_a_dataset_sha256"],
            provenance["reviewer_b_dataset_sha256"],
        )

    def test_canonical_dataset_fingerprint_is_key_order_independent(self):
        dataset_a, detection_bytes, screenshot_bytes = labelled_fixture()
        dataset_b = json.loads(json.dumps(dataset_a, sort_keys=True))
        first = evaluate_review_agreement(
            dataset_a, dataset_a, "reviewer-a", "reviewer-b",
            detection_bytes, screenshot_bytes,
        )
        second = evaluate_review_agreement(
            dataset_b, dataset_b, "reviewer-a", "reviewer-b",
            detection_bytes, screenshot_bytes,
        )
        self.assertEqual(
            first["review_dataset_provenance"]["reviewer_a_dataset_sha256"],
            second["review_dataset_provenance"]["reviewer_a_dataset_sha256"],
        )
        self.assertEqual(
            first["review_dataset_provenance"]["reviewer_a_hash_mode"],
            "canonical_json_content",
        )

    def test_rejects_raw_dataset_bytes_that_do_not_match_parsed_content(self):
        dataset_a, detection_bytes, screenshot_bytes = labelled_fixture()
        dataset_b = copy.deepcopy(dataset_a)
        raw_a = json.dumps(dataset_a).encode("utf-8")
        changed = copy.deepcopy(dataset_b)
        changed["samples"][0]["human"]["colour"] = "cyan"
        raw_b = json.dumps(changed).encode("utf-8")
        with self.assertRaisesRegex(ValueError, "do not match the parsed"):
            evaluate_review_agreement(
                dataset_a,
                dataset_b,
                "reviewer-a",
                "reviewer-b",
                detection_bytes,
                screenshot_bytes,
                raw_a,
                raw_b,
            )

    def test_rejects_same_reviewer_identifier_case_insensitively(self):
        dataset, detection_bytes, screenshot_bytes = labelled_fixture()
        with self.assertRaisesRegex(ValueError, "must be distinct"):
            evaluate_review_agreement(
                dataset,
                copy.deepcopy(dataset),
                "Reviewer-A",
                " reviewer-a ",
                detection_bytes,
                screenshot_bytes,
            )

    def test_rejects_mismatched_source_detector_bytes(self):
        dataset_a, detection_bytes, screenshot_bytes = labelled_fixture()
        with self.assertRaisesRegex(ValueError, "Source detector SHA-256"):
            evaluate_review_agreement(
                dataset_a,
                copy.deepcopy(dataset_a),
                "reviewer-a",
                "reviewer-b",
                detection_bytes + b" ",
                screenshot_bytes,
            )

    def test_rejects_mismatched_source_screenshot_bytes(self):
        dataset_a, detection_bytes, screenshot_bytes = labelled_fixture()
        with self.assertRaisesRegex(ValueError, "Source screenshot SHA-256"):
            evaluate_review_agreement(
                dataset_a,
                copy.deepcopy(dataset_a),
                "reviewer-a",
                "reviewer-b",
                detection_bytes,
                screenshot_bytes + b"x",
            )

    def test_rejects_a_modified_detector_snapshot(self):
        dataset_a, detection_bytes, screenshot_bytes = labelled_fixture()
        dataset_b = copy.deepcopy(dataset_a)
        dataset_b["samples"][0]["detector"]["colour"] = "blue"
        with self.assertRaisesRegex(ValueError, "detector snapshot"):
            evaluate_review_agreement(
                dataset_a,
                dataset_b,
                "reviewer-a",
                "reviewer-b",
                detection_bytes,
                screenshot_bytes,
            )

    def test_rejects_empty_reviewer_identifiers(self):
        dataset, detection_bytes, screenshot_bytes = labelled_fixture()
        with self.assertRaisesRegex(ValueError, "reviewer_a_id"):
            evaluate_review_agreement(
                dataset,
                copy.deepcopy(dataset),
                " ",
                "reviewer-b",
                detection_bytes,
                screenshot_bytes,
            )

    def test_kappa_is_undefined_when_expected_agreement_is_one(self):
        result = _agreement_summary(["confirmed", "confirmed"], ["confirmed", "confirmed"])
        self.assertIsNone(result["cohen_kappa"])
        self.assertEqual(
            result["cohen_kappa_status"],
            "undefined_expected_agreement_is_one",
        )

    def test_empty_agreement_support_is_reported_as_unavailable(self):
        result = _agreement_summary([], [])
        self.assertIsNone(result["agreement_rate"])
        self.assertIsNone(result["cohen_kappa"])
        self.assertEqual(result["cohen_kappa_status"], "no_eligible_pairs")


if __name__ == "__main__":
    unittest.main(verbosity=2)
