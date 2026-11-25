import copy
import json
import tempfile
import unittest
from pathlib import Path

from prepare_shooter_review_pair import prepare_review_pair
from shooter_review_intake_audit import audit_review_intake
from test_prepare_shooter_labels import fixture_artifacts


class ShooterReviewIntakeAuditTests(unittest.TestCase):
    def _pair(self, root):
        _, detection_bytes, screenshot_bytes = fixture_artifacts()
        detection = root / "detection.json"
        screenshot = root / "screenshot.png"
        detection.write_bytes(detection_bytes)
        screenshot.write_bytes(screenshot_bytes)
        result = prepare_review_pair(
            detection,
            screenshot,
            root / "review-pair",
            "reviewer-a",
            "reviewer-b",
        )
        manifest = json.loads(result["manifest"].read_text(encoding="utf-8"))
        dataset_a = json.loads(
            result["reviewer_a_dataset"].read_text(encoding="utf-8")
        )
        dataset_b = json.loads(
            result["reviewer_b_dataset"].read_text(encoding="utf-8")
        )
        return (
            result["manifest"].parent,
            manifest,
            result["reviewer_a_dataset"],
            result["reviewer_b_dataset"],
            dataset_a,
            dataset_b,
        )

    def _complete(self, dataset):
        result = copy.deepcopy(dataset)
        for sample in result["samples"]:
            detector = sample["detector"]
            sample["review_status"] = "confirmed"
            sample["human"] = {
                "visibility": "visible",
                "row": detector["row"],
                "column": detector["column"],
                "colour": "red",
                "ammunition_readable": True,
                "ammunition": 10,
            }
        result["labelled_by_user"] = True
        return result

    def _write(self, path, value):
        path.write_text(json.dumps(value), encoding="utf-8")

    def test_blank_pair_reports_zero_completion_and_not_ready(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base, manifest, _, _, _, _ = self._pair(root)
            report = audit_review_intake(
                manifest, base, "reviewer-a", "reviewer-b"
            )

        self.assertEqual(report["capture_count"], 1)
        self.assertEqual(report["sample_count"], 12)
        self.assertEqual(report["reviewer_a"]["reviewed_count"], 0)
        self.assertEqual(report["reviewer_b"]["reviewed_count"], 0)
        self.assertEqual(report["reviewer_a"]["completion_rate"], 0.0)
        self.assertFalse(report["agreement_audit_ready"])
        self.assertTrue(report["source_provenance"]["all_capture_sources_verified"])
        self.assertFalse(report["reviewer_independence_verified"])
        self.assertFalse(report["label_truth_independently_verified"])
        self.assertFalse(report["agreement_evaluated"])
        self.assertFalse(report["game_taps_enabled"])

    def test_completed_pair_is_ready_for_agreement_audit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base, manifest, path_a, path_b, dataset_a, dataset_b = self._pair(root)
            self._write(path_a, self._complete(dataset_a))
            self._write(path_b, self._complete(dataset_b))
            report = audit_review_intake(
                manifest, base, "reviewer-a", "reviewer-b"
            )

        self.assertTrue(report["agreement_audit_ready"])
        self.assertEqual(report["reviewer_a"]["reviewed_count"], 12)
        self.assertEqual(report["reviewer_b"]["reviewed_count"], 12)
        self.assertEqual(report["reviewer_a"]["completion_rate"], 1.0)
        self.assertEqual(report["reviewer_b"]["completion_rate"], 1.0)
        self.assertEqual(
            report["captures"][0]["reviewer_a"]["dataset_sha256"].__len__(),
            64,
        )

    def test_partial_review_reports_per_reviewer_progress(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base, manifest, path_a, path_b, dataset_a, dataset_b = self._pair(root)
            partial = copy.deepcopy(dataset_a)
            partial["samples"][0] = self._complete(dataset_a)["samples"][0]
            self._write(path_a, partial)
            self._write(path_b, dataset_b)
            report = audit_review_intake(
                manifest, base, "reviewer-a", "reviewer-b"
            )

        self.assertEqual(report["reviewer_a"]["reviewed_count"], 1)
        self.assertEqual(report["reviewer_a"]["not_reviewed_count"], 11)
        self.assertEqual(report["reviewer_a"]["completion_rate"], round(1 / 12, 6))
        self.assertEqual(report["reviewer_b"]["reviewed_count"], 0)
        self.assertFalse(report["agreement_audit_ready"])

    def test_ambiguous_slots_count_as_reviewed_without_human_labels(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base, manifest, path_a, path_b, dataset_a, dataset_b = self._pair(root)
            for dataset in (dataset_a, dataset_b):
                for sample in dataset["samples"]:
                    sample["review_status"] = "ambiguous"
                dataset["labelled_by_user"] = True
            self._write(path_a, dataset_a)
            self._write(path_b, dataset_b)
            report = audit_review_intake(
                manifest, base, "reviewer-a", "reviewer-b"
            )

        self.assertTrue(report["agreement_audit_ready"])
        self.assertEqual(report["reviewer_a"]["ambiguous_count"], 12)
        self.assertEqual(report["reviewer_b"]["ambiguous_count"], 12)

    def test_rejects_labelled_by_user_true_for_partial_dataset(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base, manifest, path_a, _, dataset_a, _ = self._pair(root)
            dataset_a["labelled_by_user"] = True
            self._write(path_a, dataset_a)
            with self.assertRaisesRegex(ValueError, "must be false"):
                audit_review_intake(
                    manifest, base, "reviewer-a", "reviewer-b"
                )

    def test_rejects_unreviewed_sample_with_prefilled_human_labels(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base, manifest, path_a, _, dataset_a, _ = self._pair(root)
            dataset_a["samples"][0]["human"]["visibility"] = "visible"
            self._write(path_a, dataset_a)
            with self.assertRaisesRegex(ValueError, "contains human labels"):
                audit_review_intake(
                    manifest, base, "reviewer-a", "reviewer-b"
                )

    def test_rejects_non_string_review_status(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base, manifest, path_a, _, dataset_a, _ = self._pair(root)
            dataset_a["samples"][0]["review_status"] = ["confirmed"]
            self._write(path_a, dataset_a)
            with self.assertRaisesRegex(ValueError, "invalid review_status"):
                audit_review_intake(
                    manifest, base, "reviewer-a", "reviewer-b"
                )

    def test_rejects_changed_detector_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base, manifest, path_a, _, dataset_a, _ = self._pair(root)
            dataset_a["samples"][0]["detector"]["colour"] = "cyan"
            self._write(path_a, dataset_a)
            with self.assertRaisesRegex(ValueError, "detector snapshot changed"):
                audit_review_intake(
                    manifest, base, "reviewer-a", "reviewer-b"
                )

    def test_rejects_same_dataset_file_for_both_reviewers(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base, manifest, _, _, _, _ = self._pair(root)
            entry = manifest["captures"][0]
            entry["reviewer_b_dataset"] = entry["reviewer_a_dataset"]
            with self.assertRaisesRegex(ValueError, "cannot reuse one file"):
                audit_review_intake(
                    manifest, base, "reviewer-a", "reviewer-b"
                )

    def test_rejects_same_reviewer_identifiers(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base, manifest, _, _, _, _ = self._pair(root)
            with self.assertRaisesRegex(ValueError, "must be distinct"):
                audit_review_intake(
                    manifest, base, "Reviewer-A", " reviewer-a "
                )

    def test_rejects_manifest_with_extra_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base, manifest, _, _, _, _ = self._pair(root)
            manifest["independence_verified"] = True
            with self.assertRaisesRegex(ValueError, "only schema_version and captures"):
                audit_review_intake(
                    manifest, base, "reviewer-a", "reviewer-b"
                )


if __name__ == "__main__":
    unittest.main(verbosity=2)
