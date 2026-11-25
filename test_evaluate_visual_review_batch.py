import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import evaluate_visual_review_batch as batch


def _encoded(value):
    return json.dumps(value, sort_keys=True).encode("utf-8")


def _shooter_sample(
    visibility="visible",
    detected_visibility="visible",
    reviewed_position=None,
    detected_position=None,
    reviewed_colour=None,
    detected_colour=None,
    reviewed_ammunition=None,
    detected_ammunition=None,
):
    return {
        "reviewed_visibility": visibility,
        "detected_visibility": detected_visibility,
        "reviewed_position": reviewed_position,
        "detected_position": detected_position or [1, 1],
        "reviewed_colour": reviewed_colour,
        "detected_colour": detected_colour,
        "reviewed_ammunition": reviewed_ammunition,
        "detected_ammunition": detected_ammunition,
        "ammunition_correct": (
            detected_ammunition == reviewed_ammunition
            if reviewed_ammunition is not None else None
        ),
    }


def _report(bundle_index):
    if bundle_index == 1:
        board_samples = [
            {"actual": "cyan", "predicted": "cyan"},
            {"actual": "red", "predicted": "orange"},
        ]
        shooter_samples = [
            _shooter_sample(
                reviewed_position=[1, 1], detected_position=[1, 1],
                reviewed_colour="cyan", detected_colour="cyan",
                reviewed_ammunition=40, detected_ammunition=40,
            ),
        ]
        total, confirmed, ambiguous = 1, 1, 0
        visibility_counts = {"visible": 1}
        quality_counts = {"DISTINCT_SAMPLE": 1}
        ammo_status_counts = {"PARSED_EXACT_DIGITS": 1}
    else:
        board_samples = [
            {"actual": "green", "predicted": "green"},
            {"actual": "cyan", "predicted": "cyan"},
        ]
        shooter_samples = [
            _shooter_sample(
                detected_visibility="partially_occluded",
                reviewed_position=[1, 2], detected_position=[1, 3],
                reviewed_colour="red", detected_colour="blue",
                reviewed_ammunition=20, detected_ammunition=10,
            ),
        ]
        total, confirmed, ambiguous = 2, 1, 1
        visibility_counts = {"visible": 1}
        quality_counts = {"LOW_CONTRAST": 1}
        ammo_status_counts = {"PARSED_EXACT_DIGITS": 1}

    return {
        "review_bundle_verified": True,
        "capture_identity": {
            "source_screenshot_sha256": str(bundle_index) * 64,
            "source_screenshot_size": [40, 30],
            "capture_session_id": f"session-{bundle_index}",
            "captured_at": f"2026-11-25T12:0{bundle_index}:00+00:00",
        },
        "review_artifacts_sha256": {
            "manifest_json": "a" * 64,
            "board_labels_json": "b" * 64,
            "shooter_labels_json": "c" * 64,
        },
        "source_artifacts_sha256": {
            "board_observation_json": "d" * 64,
            "shooter_detection_json": "e" * 64,
            "source_pixel_audit_json": "f" * 64,
            "source_screenshot": str(bundle_index) * 64,
        },
        "board_colour_evaluation": {
            "sample_count": len(board_samples),
            "sample_results": board_samples,
        },
        "shooter_observation_evaluation": {
            "sample_count": total,
            "confirmed_sample_count": confirmed,
            "ambiguous_sample_count": ambiguous,
            "sample_results": shooter_samples,
            "review_coverage": {
                "confirmed_visibility_counts": visibility_counts,
                "visible_sample_quality_status_counts": quality_counts,
                "visible_ammunition_ocr_status_counts": ammo_status_counts,
            },
        },
    }


class VisualReviewBatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.batch_path = self.root / "batch.json"
        self.entries = [
            {
                "id": f"capture-{index}",
                "manifest": f"capture-{index}/manifest.json",
                "board_labels": f"capture-{index}/board-labels.json",
                "shooter_labels": f"capture-{index}/shooter-labels.json",
                "board_observation": f"capture-{index}/board.json",
                "shooter_detection": f"capture-{index}/detection.json",
                "pixel_audit": f"capture-{index}/audit.json",
                "source_screenshot": f"capture-{index}/source.png",
            }
            for index in (1, 2)
        ]
        self._write_batch()

    def tearDown(self):
        self.tmp.cleanup()

    def _write_batch(self, bundles=None, schema_version=1):
        self.batch_path.write_bytes(_encoded({
            "schema_version": schema_version,
            "bundles": self.entries if bundles is None else bundles,
        }))

    def test_pools_board_and_shooter_metrics_separately(self):
        with patch.object(
            batch, "evaluate_visual_review_bundle",
            side_effect=[_report(1), _report(2)],
        ) as evaluator:
            report = batch.evaluate_batch(self.batch_path)

        self.assertEqual(evaluator.call_count, 2)
        self.assertEqual(report["bundle_count"], 2)
        self.assertEqual(
            report["bundles"][0]["source_artifacts_sha256"]["source_screenshot"],
            report["bundles"][0]["capture_identity"]["source_screenshot_sha256"],
        )
        self.assertEqual(len(report["bundles"][0]["source_artifacts_sha256"]), 4)
        self.assertEqual(len(report["bundles"][0]["review_artifacts_sha256"]), 3)
        self.assertEqual(report["board_colour_evaluation"]["sample_count"], 4)
        self.assertEqual(report["board_colour_evaluation"]["correct_count"], 3)
        self.assertEqual(report["board_colour_evaluation"]["accuracy"], 0.75)
        self.assertEqual(report["board_colour_evaluation"]["per_class"]["cyan"]["support"], 2)
        self.assertEqual(report["board_colour_evaluation"]["per_class"]["red"]["recall"], 0.0)

        shooter = report["shooter_observation_evaluation"]
        self.assertEqual(shooter["sample_count"], 3)
        self.assertEqual(shooter["confirmed_sample_count"], 2)
        self.assertEqual(shooter["ambiguous_sample_count"], 1)
        self.assertEqual(shooter["metrics"]["visibility"]["support"], 2)
        self.assertEqual(shooter["metrics"]["visibility"]["correct_count"], 1)
        self.assertEqual(shooter["metrics"]["slot_position_alignment"]["support"], 2)
        self.assertEqual(shooter["metrics"]["slot_position_alignment"]["correct_count"], 1)
        self.assertEqual(shooter["metrics"]["colour"]["support"], 2)
        self.assertEqual(shooter["metrics"]["colour"]["correct_count"], 1)
        self.assertEqual(shooter["metrics"]["ammunition"]["support"], 2)
        self.assertEqual(shooter["metrics"]["ammunition"]["exact_match_count"], 1)
        self.assertEqual(
            shooter["metrics"]["ammunition"]["mean_absolute_error_on_detected_readings"],
            5.0,
        )
        self.assertFalse(report["label_truth_independently_verified"])
        self.assertFalse(report["gameplay_verified"])
        self.assertFalse(report["game_taps_enabled"])
        self.assertEqual(report["batch_sha256"], hashlib.sha256(
            self.batch_path.read_bytes()
        ).hexdigest())
        self.assertTrue(batch.verify_batch_report(report))
        unsigned = dict(report)
        digest = unsigned.pop("evaluation_sha256")
        self.assertEqual(
            digest, hashlib.sha256(batch._canonical_json_bytes(unsigned)).hexdigest()
        )

    def test_rejects_modified_saved_batch_report(self):
        with patch.object(
            batch, "evaluate_visual_review_bundle",
            side_effect=[_report(1), _report(2)],
        ):
            report = batch.evaluate_batch(self.batch_path)
        report["interpretation"] += " modified"
        with self.assertRaisesRegex(ValueError, "does not match evaluation_sha256"):
            batch.verify_batch_report(report)

    def test_rejects_invalid_saved_batch_report_digest(self):
        with patch.object(
            batch, "evaluate_visual_review_bundle",
            side_effect=[_report(1), _report(2)],
        ):
            report = batch.evaluate_batch(self.batch_path)
        report["evaluation_sha256"] = "z" * 64
        with self.assertRaisesRegex(ValueError, "evaluation_sha256 is invalid"):
            batch.verify_batch_report(report)

    def test_rejects_duplicate_screenshot(self):
        first = _report(1)
        second = _report(2)
        second["capture_identity"]["source_screenshot_sha256"] = (
            first["capture_identity"]["source_screenshot_sha256"]
        )
        second["source_artifacts_sha256"]["source_screenshot"] = (
            first["source_artifacts_sha256"]["source_screenshot"]
        )
        with patch.object(
            batch, "evaluate_visual_review_bundle", side_effect=[first, second]
        ):
            with self.assertRaisesRegex(ValueError, "Duplicate source screenshot"):
                batch.evaluate_batch(self.batch_path)

    def test_rejects_non_hex_screenshot_digest(self):
        first = _report(1)
        first["capture_identity"]["source_screenshot_sha256"] = "g" * 64
        with patch.object(
            batch, "evaluate_visual_review_bundle", side_effect=[first, _report(2)]
        ):
            with self.assertRaisesRegex(ValueError, "screenshot hash is invalid"):
                batch.evaluate_batch(self.batch_path)

    def test_rejects_missing_review_artifact_hashes(self):
        first = _report(1)
        first.pop("review_artifacts_sha256")
        with patch.object(
            batch, "evaluate_visual_review_bundle", side_effect=[first, _report(2)]
        ):
            with self.assertRaisesRegex(ValueError, "review artifact hashes are missing"):
                batch.evaluate_batch(self.batch_path)

    def test_rejects_missing_source_artifact_hashes(self):
        first = _report(1)
        first.pop("source_artifacts_sha256")
        with patch.object(
            batch, "evaluate_visual_review_bundle", side_effect=[first, _report(2)]
        ):
            with self.assertRaisesRegex(ValueError, "source artifact hashes are missing"):
                batch.evaluate_batch(self.batch_path)

    def test_rejects_source_screenshot_hash_identity_mismatch(self):
        first = _report(1)
        first["source_artifacts_sha256"]["source_screenshot"] = "9" * 64
        with patch.object(
            batch, "evaluate_visual_review_bundle", side_effect=[first, _report(2)]
        ):
            with self.assertRaisesRegex(ValueError, "disagrees with capture identity"):
                batch.evaluate_batch(self.batch_path)

    def test_rejects_duplicate_capture_session(self):
        first = _report(1)
        second = _report(2)
        second["capture_identity"]["capture_session_id"] = (
            first["capture_identity"]["capture_session_id"]
        )
        with patch.object(
            batch, "evaluate_visual_review_bundle", side_effect=[first, second]
        ):
            with self.assertRaisesRegex(ValueError, "Duplicate capture session"):
                batch.evaluate_batch(self.batch_path)

    def test_rejects_duplicate_bundle_ids_before_evaluation(self):
        entries = [dict(self.entries[0]), dict(self.entries[1])]
        entries[1]["id"] = entries[0]["id"]
        self._write_batch(entries)
        with patch.object(batch, "evaluate_visual_review_bundle") as evaluator:
            with self.assertRaisesRegex(ValueError, "Duplicate bundle id"):
                batch.evaluate_batch(self.batch_path)
        evaluator.assert_not_called()

    def test_rejects_paths_that_escape_batch_directory(self):
        entries = [dict(item) for item in self.entries]
        entries[0]["manifest"] = "../outside.json"
        self._write_batch(entries)
        with patch.object(batch, "evaluate_visual_review_bundle") as evaluator:
            with self.assertRaisesRegex(ValueError, "stay inside"):
                batch.evaluate_batch(self.batch_path)
        evaluator.assert_not_called()

    def test_rejects_single_bundle_batch(self):
        self._write_batch([self.entries[0]])
        with self.assertRaisesRegex(ValueError, "at least two"):
            batch.evaluate_batch(self.batch_path)

    def test_rejects_unsupported_schema(self):
        self._write_batch(schema_version=True)
        with self.assertRaisesRegex(ValueError, "schema_version"):
            batch.evaluate_batch(self.batch_path)

    def test_rejects_inconsistent_shooter_review_counts(self):
        first = _report(1)
        first["shooter_observation_evaluation"]["ambiguous_sample_count"] = 1
        with patch.object(
            batch, "evaluate_visual_review_bundle", side_effect=[first, _report(2)]
        ):
            with self.assertRaisesRegex(ValueError, "do not equal sample_count"):
                batch.evaluate_batch(self.batch_path)


if __name__ == "__main__":
    unittest.main()
