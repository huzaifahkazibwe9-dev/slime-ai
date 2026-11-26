import copy
import hashlib
import io
import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from PIL import Image

from prepare_shooter_review_pair import prepare_review_pair
from shooter_review_intake_audit import audit_review_intake, main
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

    def _second_capture(self, root, *, reuse_screenshot=False):
        _, detection_bytes, _ = fixture_artifacts()
        detection_data = json.loads(detection_bytes)
        if reuse_screenshot:
            screenshot_bytes = (root / "screenshot.png").read_bytes()
        else:
            image_buffer = io.BytesIO()
            Image.new("RGB", (1080, 2220), (70, 80, 90)).save(
                image_buffer, format="PNG"
            )
            screenshot_bytes = image_buffer.getvalue()
        detection_data["capture_provenance"]["source_sha256"] = (
            hashlib.sha256(screenshot_bytes).hexdigest()
        )
        detection_data["capture_provenance"]["capture_session_id"] = (
            "session-second"
        )
        detection_data["capture_provenance"]["captured_at"] = (
            "2026-11-25T13:00:00+00:00"
        )
        detection_bytes = json.dumps(
            detection_data, separators=(",", ":")
        ).encode("utf-8")
        detection_path = root / "detection-2.json"
        screenshot_path = root / "screenshot-2.png"
        detection_path.write_bytes(detection_bytes)
        screenshot_path.write_bytes(screenshot_bytes)
        pair = prepare_review_pair(
            detection_path,
            screenshot_path,
            root / "pair-2",
            "reviewer-a",
            "reviewer-b",
        )
        return {
            "reviewer_a_dataset": pair["reviewer_a_dataset"],
            "reviewer_b_dataset": pair["reviewer_b_dataset"],
            "detection": detection_path,
            "screenshot": screenshot_path,
        }

    def _two_capture_manifest(self, root, second):
        return {
            "schema_version": 1,
            "captures": [
                {
                    "reviewer_a_dataset": "review-pair/reviewer-a.json",
                    "reviewer_b_dataset": "review-pair/reviewer-b.json",
                    "detection": "detection.json",
                    "screenshot": "screenshot.png",
                },
                {
                    "reviewer_a_dataset": str(
                        second["reviewer_a_dataset"].relative_to(root)
                    ),
                    "reviewer_b_dataset": str(
                        second["reviewer_b_dataset"].relative_to(root)
                    ),
                    "detection": second["detection"].name,
                    "screenshot": second["screenshot"].name,
                },
            ],
        }

    def test_multi_capture_progress_aggregates_only_distinct_source_pairs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base, _, _, _, _, _ = self._pair(root)
            second = self._second_capture(root)
            manifest = self._two_capture_manifest(root, second)
            second_a = json.loads(
                second["reviewer_a_dataset"].read_text(encoding="utf-8")
            )
            second_b = json.loads(
                second["reviewer_b_dataset"].read_text(encoding="utf-8")
            )
            self._write(
                second["reviewer_a_dataset"], self._complete(second_a)
            )
            self._write(
                second["reviewer_b_dataset"], self._complete(second_b)
            )
            report = audit_review_intake(
                manifest, root, "reviewer-a", "reviewer-b"
            )

        self.assertEqual(report["capture_count"], 2)
        self.assertEqual(report["sample_count"], 24)
        self.assertEqual(report["reviewer_a"]["sample_count"], 24)
        self.assertEqual(report["reviewer_a"]["reviewed_count"], 12)
        self.assertEqual(report["reviewer_b"]["reviewed_count"], 12)
        self.assertEqual(report["reviewer_a"]["completion_rate"], 0.5)
        self.assertFalse(report["agreement_audit_ready"])

    def test_all_multi_capture_pairs_must_be_complete_before_ready(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base, _, path_a, path_b, dataset_a, dataset_b = self._pair(root)
            second = self._second_capture(root)
            manifest = self._two_capture_manifest(root, second)
            self._write(path_a, self._complete(dataset_a))
            self._write(path_b, self._complete(dataset_b))
            second_a = json.loads(
                second["reviewer_a_dataset"].read_text(encoding="utf-8")
            )
            second_b = json.loads(
                second["reviewer_b_dataset"].read_text(encoding="utf-8")
            )
            self._write(
                second["reviewer_a_dataset"], self._complete(second_a)
            )
            self._write(
                second["reviewer_b_dataset"], self._complete(second_b)
            )
            report = audit_review_intake(
                manifest, root, "reviewer-a", "reviewer-b"
            )

        self.assertEqual(report["capture_count"], 2)
        self.assertTrue(report["agreement_audit_ready"])
        self.assertEqual(report["reviewer_a"]["reviewed_count"], 24)
        self.assertEqual(report["reviewer_b"]["reviewed_count"], 24)
        self.assertEqual(report["reviewer_a"]["completion_rate"], 1.0)
        self.assertEqual(report["reviewer_b"]["completion_rate"], 1.0)

    def test_rejects_repeated_screenshot_across_distinct_capture_sessions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base, _, _, _, _, _ = self._pair(root)
            second = self._second_capture(root, reuse_screenshot=True)
            manifest = self._two_capture_manifest(root, second)
            with self.assertRaisesRegex(
                ValueError, "repeats an identical source screenshot"
            ):
                audit_review_intake(
                    manifest, root, "reviewer-a", "reviewer-b"
                )

    def test_rejects_reusing_a_reviewer_dataset_across_captures(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base, _, _, _, _, _ = self._pair(root)
            second = self._second_capture(root)
            manifest = self._two_capture_manifest(root, second)
            manifest["captures"][1]["reviewer_a_dataset"] = (
                manifest["captures"][0]["reviewer_a_dataset"]
            )
            with self.assertRaisesRegex(
                ValueError, "reuses a reviewer dataset file"
            ):
                audit_review_intake(
                    manifest, root, "reviewer-a", "reviewer-b"
                )

    def test_require_ready_saves_report_then_exits_nonzero_for_incomplete_pair(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base, _, _, _, _, _ = self._pair(root)
            output = root / "reports" / "intake.json"
            with patch(
                "sys.argv",
                [
                    "shooter_review_intake_audit.py",
                    str(base / "review_manifest.json"),
                    "--reviewer-a-id", "reviewer-a",
                    "--reviewer-b-id", "reviewer-b",
                    "--output", str(output),
                    "--require-ready",
                ],
            ):
                with self.assertRaises(SystemExit) as error:
                    main()

            self.assertEqual(error.exception.code, 1)
            self.assertTrue(output.is_file())
            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertFalse(report["agreement_audit_ready"])
            self.assertEqual(report["reviewer_a"]["not_reviewed_count"], 12)

    def test_require_ready_exits_successfully_for_complete_pair(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base, _, path_a, path_b, dataset_a, dataset_b = self._pair(root)
            self._write(path_a, self._complete(dataset_a))
            self._write(path_b, self._complete(dataset_b))
            output = root / "reports" / "intake.json"
            with patch(
                "sys.argv",
                [
                    "shooter_review_intake_audit.py",
                    str(base / "review_manifest.json"),
                    "--reviewer-a-id", "reviewer-a",
                    "--reviewer-b-id", "reviewer-b",
                    "--output", str(output),
                    "--require-ready",
                ],
            ):
                main()

            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertTrue(report["agreement_audit_ready"])
            self.assertEqual(report["reviewer_a"]["not_reviewed_count"], 0)
            self.assertEqual(report["reviewer_b"]["not_reviewed_count"], 0)

    def test_require_ready_rejects_complete_all_ambiguous_pair(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base, _, path_a, path_b, dataset_a, dataset_b = self._pair(root)
            for path, dataset in ((path_a, dataset_a), (path_b, dataset_b)):
                for sample in dataset["samples"]:
                    sample["review_status"] = "ambiguous"
                dataset["labelled_by_user"] = True
                self._write(path, dataset)

            output = root / "reports" / "intake.json"
            with patch(
                "sys.argv",
                [
                    "shooter_review_intake_audit.py",
                    str(base / "review_manifest.json"),
                    "--reviewer-a-id", "reviewer-a",
                    "--reviewer-b-id", "reviewer-b",
                    "--output", str(output),
                    "--require-ready",
                ],
            ):
                with self.assertRaises(SystemExit) as error:
                    main()

            self.assertEqual(error.exception.code, 1)
            self.assertTrue(output.is_file())
            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertTrue(report["reviewer_a"]["complete"])
            self.assertTrue(report["reviewer_b"]["complete"])
            self.assertFalse(report["reviewer_a"]["agreement_eligible"])
            self.assertFalse(report["reviewer_b"]["agreement_eligible"])
            self.assertFalse(report["agreement_audit_ready"])
            self.assertEqual(
                report["readiness_blockers"][0]["blockers"],
                [
                    "reviewer_a_has_no_confirmed_samples",
                    "reviewer_b_has_no_confirmed_samples",
                ],
            )
            self.assertFalse(report["game_taps_enabled"])

    def test_cli_refuses_to_overwrite_any_review_input(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base, _, path_a, _, _, _ = self._pair(root)
            manifest_path = base / "review_manifest.json"
            original = path_a.read_bytes()
            with patch(
                "sys.argv",
                [
                    "shooter_review_intake_audit.py",
                    str(manifest_path),
                    "--reviewer-a-id", "reviewer-a",
                    "--reviewer-b-id", "reviewer-b",
                    "--output", str(path_a),
                ],
            ):
                with self.assertRaises(SystemExit) as error:
                    main()

            self.assertEqual(error.exception.code, 2)
            self.assertEqual(path_a.read_bytes(), original)

    def test_cli_writes_report_to_new_output_path(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base, _, _, _, _, _ = self._pair(root)
            output = root / "reports" / "intake.json"
            with patch(
                "sys.argv",
                [
                    "shooter_review_intake_audit.py",
                    str(base / "review_manifest.json"),
                    "--reviewer-a-id", "reviewer-a",
                    "--reviewer-b-id", "reviewer-b",
                    "--output", str(output),
                ],
            ):
                main()

            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertFalse(report["agreement_audit_ready"])
            self.assertEqual(report["capture_count"], 1)
            self.assertFalse(report["game_taps_enabled"])

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

        self.assertTrue(report["reviewer_a"]["complete"])
        self.assertTrue(report["reviewer_b"]["complete"])
        self.assertFalse(report["reviewer_a"]["agreement_eligible"])
        self.assertFalse(report["reviewer_b"]["agreement_eligible"])
        self.assertFalse(report["agreement_audit_ready"])
        self.assertEqual(report["reviewer_a"]["ambiguous_count"], 12)
        self.assertEqual(report["reviewer_b"]["ambiguous_count"], 12)
        self.assertEqual(
            report["readiness_blockers"][0]["blockers"],
            [
                "reviewer_a_has_no_confirmed_samples",
                "reviewer_b_has_no_confirmed_samples",
            ],
        )

    def test_complete_mixed_reviews_are_agreement_eligible(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base, manifest, path_a, path_b, dataset_a, dataset_b = self._pair(root)
            for path, dataset in (
                (path_a, dataset_a),
                (path_b, dataset_b),
            ):
                completed = self._complete(dataset)
                for index in range(1, len(completed["samples"])):
                    completed["samples"][index]["review_status"] = "ambiguous"
                    completed["samples"][index]["human"] = copy.deepcopy(
                        dataset["samples"][index]["human"]
                    )
                self._write(path, completed)

            report = audit_review_intake(
                manifest, base, "reviewer-a", "reviewer-b"
            )

        self.assertTrue(report["agreement_audit_ready"])
        self.assertTrue(report["captures"][0]["paired_review_complete"])
        self.assertTrue(report["captures"][0]["paired_agreement_eligible"])
        self.assertEqual(report["reviewer_a"]["confirmed_count"], 1)
        self.assertEqual(report["reviewer_b"]["confirmed_count"], 1)
        self.assertEqual(report["readiness_blockers"], [])

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
