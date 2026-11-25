import copy
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from prepare_shooter_labels import build_template
from shooter_batch_review_agreement import evaluate_agreement_manifest
from test_shooter_observation_evaluation import labelled_fixture
from test_prepare_shooter_labels import fixture_artifacts


def _second_reviewed_capture(session_id, colour):
    base, _, _ = labelled_fixture()
    detection, _, _ = fixture_artifacts()
    image_buffer = io.BytesIO()
    Image.new("RGB", (1080, 2220), colour).save(image_buffer, format="PNG")
    screenshot_bytes = image_buffer.getvalue()
    detection["capture_provenance"]["source_sha256"] = hashlib.sha256(
        screenshot_bytes
    ).hexdigest()
    detection["capture_provenance"]["capture_session_id"] = session_id
    detection["capture_provenance"]["captured_at"] = (
        "2026-11-25T13:00:00+00:00"
    )
    detection_bytes = json.dumps(
        detection, separators=(",", ":")
    ).encode("utf-8")
    dataset = build_template(detection, detection_bytes, screenshot_bytes)
    dataset["labelled_by_user"] = True
    for target, source in zip(dataset["samples"], base["samples"]):
        target["review_status"] = source["review_status"]
        target["human"] = copy.deepcopy(source["human"])
    return dataset, detection_bytes, screenshot_bytes


def _write_pair(root, index, colour):
    dataset_a, detection_bytes, screenshot_bytes = labelled_fixture()
    dataset_b, detection_b, screenshot_b = _second_reviewed_capture(
        f"session-{index}", colour
    )
    # The fixture generator is deterministic except for the changed source
    # screenshot and provenance. Both label files refer to this same capture.
    dataset_a, detection_bytes, screenshot_bytes = dataset_b, detection_b, screenshot_b
    dataset_b = copy.deepcopy(dataset_a)
    dataset_a_path = root / f"a-{index}.json"
    dataset_b_path = root / f"b-{index}.json"
    detection_path = root / f"detection-{index}.json"
    screenshot_path = root / f"screenshot-{index}.png"
    dataset_a_path.write_text(json.dumps(dataset_a), encoding="utf-8")
    dataset_b_path.write_text(json.dumps(dataset_b), encoding="utf-8")
    detection_path.write_bytes(detection_bytes)
    screenshot_path.write_bytes(screenshot_bytes)
    return {
        "reviewer_a_dataset": dataset_a_path.name,
        "reviewer_b_dataset": dataset_b_path.name,
        "detection": detection_path.name,
        "screenshot": screenshot_path.name,
        "session_id": f"session-{index}",
        "dataset_b_path": dataset_b_path,
    }


class ShooterBatchReviewAgreementTests(unittest.TestCase):
    def test_aggregates_distinct_source_verified_captures(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = _write_pair(root, 1, (10, 20, 30))
            second = _write_pair(root, 2, (30, 40, 50))
            manifest = {
                "schema_version": 1,
                "captures": [
                    {
                        key: first[key]
                        for key in (
                            "reviewer_a_dataset", "reviewer_b_dataset",
                            "detection", "screenshot",
                        )
                    },
                    {
                        key: second[key]
                        for key in (
                            "reviewer_a_dataset", "reviewer_b_dataset",
                            "detection", "screenshot",
                        )
                    },
                ],
            }

            report = evaluate_agreement_manifest(
                manifest, root, "reviewer-a", "reviewer-b"
            )

        self.assertEqual(report["capture_count"], 2)
        self.assertEqual(report["sample_count"], 24)
        self.assertEqual(report["both_confirmed_sample_count"], 24)
        self.assertEqual(report["disagreement_count"], 0)
        reviewer_provenance = report["captures"][0][
            "review_dataset_provenance"
        ]
        self.assertEqual(
            reviewer_provenance["reviewer_a_hash_mode"], "raw_file_bytes"
        )
        self.assertEqual(
            reviewer_provenance["reviewer_b_hash_mode"], "raw_file_bytes"
        )
        self.assertEqual(
            len(reviewer_provenance["reviewer_a_dataset_sha256"]), 64
        )
        self.assertEqual(
            len(reviewer_provenance["reviewer_b_dataset_sha256"]), 64
        )
        self.assertEqual(
            report["field_agreement"]["visibility"]["agreement_rate"], 1.0
        )
        self.assertEqual(
            report["field_agreement"]["visibility"]["support"], 24
        )
        self.assertEqual(
            report["field_agreement"]["ammunition_exact_value"]["support"], 8
        )
        self.assertEqual(
            report["per_slot_agreement"]["top_1"]["field_agreement"][
                "colour"
            ]["agreement_rate"],
            1.0,
        )
        self.assertEqual(
            report["per_slot_agreement"]["top_1"]["field_agreement"][
                "colour"
            ]["support"],
            2,
        )
        self.assertEqual(
            report["field_agreement"]["visibility"]["cohen_kappa_status"],
            "not_pooled_across_captures",
        )
        self.assertTrue(
            report["source_provenance"]["all_capture_sources_verified"]
        )
        self.assertFalse(report["reviewer_independence_verified"])
        self.assertFalse(report["label_truth_independently_verified"])
        self.assertFalse(report["gameplay_verified"])
        self.assertFalse(report["game_taps_enabled"])

    def test_rejects_duplicate_capture_session(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = _write_pair(root, 1, (10, 20, 30))
            entry = {
                key: first[key]
                for key in (
                    "reviewer_a_dataset", "reviewer_b_dataset",
                    "detection", "screenshot",
                )
            }
            manifest = {"schema_version": 1, "captures": [entry, entry]}
            with self.assertRaisesRegex(ValueError, "repeats capture session_id"):
                evaluate_agreement_manifest(
                    manifest, root, "reviewer-a", "reviewer-b"
                )

    def test_rejects_repeated_screenshot_across_manifest_entries(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = _write_pair(root, 1, (10, 20, 30))
            # Same original screenshot bytes, but a distinct capture session
            # and detector JSON, isolates duplicate-image manifest rejection.
            second = _write_pair(root, 2, (10, 20, 30))
            manifest = {
                "schema_version": 1,
                "captures": [
                    {
                        key: first[key]
                        for key in (
                            "reviewer_a_dataset", "reviewer_b_dataset",
                            "detection", "screenshot",
                        )
                    },
                    {
                        key: second[key]
                        for key in (
                            "reviewer_a_dataset", "reviewer_b_dataset",
                            "detection", "screenshot",
                        )
                    },
                ],
            }
            with self.assertRaisesRegex(ValueError, "Manifest repeats an identical source screenshot"):
                evaluate_agreement_manifest(
                    manifest, root, "reviewer-a", "reviewer-b"
                )

    def test_rejects_empty_manifest(self):
        with self.assertRaisesRegex(ValueError, "non-empty list"):
            evaluate_agreement_manifest(
                {"schema_version": 1, "captures": []},
                ".",
                "reviewer-a",
                "reviewer-b",
            )

    def test_rejects_duplicate_reviewer_ids(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = _write_pair(root, 1, (10, 20, 30))
            manifest = {
                "schema_version": 1,
                "captures": [{
                    key: first[key]
                    for key in (
                        "reviewer_a_dataset", "reviewer_b_dataset",
                        "detection", "screenshot",
                    )
                }],
            }
            with self.assertRaisesRegex(ValueError, "must be distinct"):
                evaluate_agreement_manifest(
                    manifest, root, "reviewer-a", "Reviewer-A"
                )


if __name__ == "__main__":
    unittest.main(verbosity=2)
