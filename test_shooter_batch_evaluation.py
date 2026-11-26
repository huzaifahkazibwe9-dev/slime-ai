import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from prepare_shooter_labels import build_template
from shooter_batch_evaluation import evaluate_manifest
from test_prepare_shooter_labels import fixture_artifacts


def write_capture(root, index, screenshot_colour, session_id=None, screenshot_bytes_override=None):
    detection, _, _ = fixture_artifacts()
    if screenshot_bytes_override is None:
        buffer = io.BytesIO()
        Image.new("RGB", (1080, 2220), screenshot_colour).save(buffer, format="PNG")
        screenshot_bytes = buffer.getvalue()
    else:
        screenshot_bytes = screenshot_bytes_override
    detection["capture_provenance"]["source_sha256"] = hashlib.sha256(
        screenshot_bytes
    ).hexdigest()
    detection["capture_provenance"]["capture_session_id"] = (
        session_id or f"batch-session-{index}"
    )
    detection["capture_provenance"]["captured_at"] = (
        f"2026-11-25T12:{index:02d}:00+00:00"
    )
    detection_bytes = json.dumps(
        detection, separators=(",", ":")
    ).encode("utf-8")
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

    dataset_path = root / f"labels-{index}.json"
    detection_path = root / f"detection-{index}.json"
    screenshot_path = root / f"screenshot-{index}.png"
    dataset_path.write_text(json.dumps(dataset), encoding="utf-8")
    detection_path.write_bytes(detection_bytes)
    screenshot_path.write_bytes(screenshot_bytes)
    return {
        "dataset": dataset_path.name,
        "detection": detection_path.name,
        "screenshot": screenshot_path.name,
        "dataset_object": dataset,
        "detection_bytes": detection_bytes,
        "screenshot_bytes": screenshot_bytes,
    }


class ShooterBatchEvaluationTests(unittest.TestCase):
    def test_aggregates_metrics_across_distinct_capture_sessions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = write_capture(root, 1, (10, 20, 30))
            second = write_capture(root, 2, (30, 40, 50))
            second["dataset_object"]["samples"][0]["human"]["colour"] = "cyan"
            second["dataset_object"]["samples"][0]["human"]["ammunition"] += 1
            (root / second["dataset"]).write_text(
                json.dumps(second["dataset_object"]), encoding="utf-8"
            )
            manifest = {
                "schema_version": 1,
                "captures": [
                    {key: first[key] for key in ("dataset", "detection", "screenshot")},
                    {key: second[key] for key in ("dataset", "detection", "screenshot")},
                ],
            }

            report = evaluate_manifest(manifest, base_dir=root)

        self.assertEqual(report["capture_count"], 2)
        self.assertEqual(report["sample_count"], 24)
        self.assertEqual(report["confirmed_sample_count"], 24)
        self.assertEqual(report["metrics"]["visibility"]["support"], 24)
        self.assertEqual(report["metrics"]["visibility"]["accuracy"], 1.0)
        self.assertEqual(report["metrics"]["visibility"]["accuracy_interval_95"], {
            "method": "wilson_score",
            "confidence_level": 0.95,
            "lower": 0.862024,
            "upper": 1.0,
        })
        self.assertEqual(report["metrics"]["slot_position_alignment"]["support"], 24)
        self.assertEqual(report["metrics"]["colour"]["support"], 8)
        self.assertEqual(report["metrics"]["colour"]["accuracy"], 0.875)
        self.assertEqual(report["metrics"]["colour"]["accuracy_interval_95"], {
            "method": "wilson_score",
            "confidence_level": 0.95,
            "lower": 0.529112,
            "upper": 0.977583,
        })
        self.assertEqual(report["metrics"]["ammunition"]["support"], 8)
        self.assertEqual(report["metrics"]["ammunition"]["exact_match_count"], 7)
        self.assertEqual(report["metrics"]["ammunition"]["exact_match_accuracy"], 0.875)
        self.assertEqual(report["metrics"]["ammunition"]["exact_match_accuracy_interval_95"], {
            "method": "wilson_score",
            "confidence_level": 0.95,
            "lower": 0.529112,
            "upper": 0.977583,
        })
        self.assertTrue(report["source_provenance"]["all_source_artifacts_verified"])
        self.assertFalse(report["coverage_adequacy_assessed"])

        coverage = report["coverage_profile"]
        self.assertEqual(
            coverage["panel_positions_with_confirmed_labels"], 12
        )
        self.assertEqual(
            coverage["detector_panel_position_review_counts"]["r1c1"],
            {"confirmed": 2, "ambiguous": 0},
        )
        self.assertEqual(
            coverage["human_visibility_class_support"],
            {
                "visible": 8, "unrevealed": 8,
                "partially_occluded": 8, "empty": 0,
            },
        )
        self.assertEqual(
            coverage["human_visible_colour_support"]["red"], 7
        )
        self.assertEqual(
            coverage["human_visible_colour_support"]["cyan"], 1
        )
        self.assertEqual(
            coverage["human_legible_ammunition_value_support"],
            [
                {"value": 11, "count": 1},
                {"value": 12, "count": 3},
                {"value": 13, "count": 2},
                {"value": 14, "count": 2},
            ],
        )
        self.assertFalse(coverage["coverage_adequacy_assessed"])
        self.assertEqual(report["review_follow_up"]["panel_review_targets"], [])
        self.assertEqual(
            report["review_follow_up"][
                "visibility_classes_with_zero_confirmed_support"
            ],
            ["empty"],
        )
        self.assertEqual(
            report["review_follow_up"][
                "visible_colour_classes_with_zero_confirmed_support"
            ],
            [
                label for label in (
                    "black", "white", "gray", "brown", "orange", "yellow",
                    "green", "blue", "purple", "magenta",
                )
            ],
        )
        self.assertEqual(
            report["captures"][0]["review_follow_up"]["panel_review_targets"],
            [],
        )
        self.assertEqual(
            report["captures"][0]["coverage_profile"][
                "panel_positions_with_confirmed_labels"
            ],
            12,
        )
        self.assertFalse(report["label_truth_independently_verified"])
        self.assertFalse(report["gameplay_verified"])
        self.assertFalse(report["game_taps_enabled"])

    def test_reports_ambiguous_panel_positions_and_unrepresented_classes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            capture = write_capture(root, 1, (10, 20, 30))
            dataset = capture["dataset_object"]
            dataset["samples"][0]["review_status"] = "ambiguous"
            dataset["samples"][0]["human"] = {
                "visibility": "", "row": None, "column": None,
                "colour": "", "ammunition_readable": None, "ammunition": None,
            }
            (root / capture["dataset"]).write_text(
                json.dumps(dataset), encoding="utf-8"
            )
            manifest = {
                "schema_version": 1,
                "captures": [{
                    key: capture[key]
                    for key in ("dataset", "detection", "screenshot")
                }],
            }

            report = evaluate_manifest(manifest, base_dir=root)

        coverage = report["coverage_profile"]
        self.assertEqual(
            coverage["detector_panel_position_review_counts"]["r1c1"],
            {"confirmed": 0, "ambiguous": 1},
        )
        self.assertEqual(
            coverage["panel_positions_with_confirmed_labels"], 11
        )
        self.assertEqual(
            coverage["panel_positions_with_only_ambiguous_labels"], 1
        )
        self.assertEqual(
            coverage["human_visibility_class_support"]["empty"], 0
        )
        self.assertEqual(
            coverage["human_visible_colour_support"]["cyan"], 0
        )
        self.assertFalse(coverage["coverage_adequacy_assessed"])
        self.assertFalse(report["coverage_adequacy_assessed"])
        targets = report["review_follow_up"]["panel_review_targets"]
        self.assertEqual(targets[0], {
            "position": "r1c1",
            "status": "ambiguous_only",
            "confirmed_count": 0,
            "ambiguous_count": 1,
        })
        self.assertEqual(
            report["review_follow_up"][
                "visibility_classes_with_zero_confirmed_support"
            ],
            ["empty"],
        )
        self.assertFalse(report["review_follow_up"]["coverage_adequacy_assessed"])


    def test_empty_aggregate_metrics_report_unavailable_intervals(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            capture = write_capture(root, 1, (10, 20, 30))
            dataset = capture["dataset_object"]
            for sample in dataset["samples"]:
                sample["human"] = {
                    "visibility": "unrevealed",
                    "row": None,
                    "column": None,
                    "colour": "",
                    "ammunition_readable": False,
                    "ammunition": None,
                }
            (root / capture["dataset"]).write_text(
                json.dumps(dataset), encoding="utf-8"
            )
            manifest = {
                "schema_version": 1,
                "captures": [{
                    key: capture[key]
                    for key in ("dataset", "detection", "screenshot")
                }],
            }

            report = evaluate_manifest(manifest, base_dir=root)

        self.assertIsNone(
            report["metrics"]["slot_position_alignment"]["accuracy_interval_95"]
        )
        self.assertIsNone(report["metrics"]["colour"]["accuracy_interval_95"])
        self.assertIsNone(
            report["metrics"]["ammunition"]["exact_match_accuracy_interval_95"]
        )



    def test_single_capture_aggregate_metrics_match_capture_metrics(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            capture = write_capture(root, 1, (10, 20, 30))
            manifest = {
                "schema_version": 1,
                "captures": [{
                    key: capture[key]
                    for key in ("dataset", "detection", "screenshot")
                }],
            }

            report = evaluate_manifest(manifest, base_dir=root)

        aggregate = report["metrics"]
        single_capture = report["captures"][0]["metrics"]
        for metric_name in (
            "visibility", "slot_position_alignment", "colour"
        ):
            with self.subTest(metric=metric_name):
                self.assertEqual(aggregate[metric_name], single_capture[metric_name])
                self.assertIn("macro_f1", aggregate[metric_name])
                self.assertIn("per_class", aggregate[metric_name])
        self.assertIn("visible", aggregate["visibility"]["per_class"])


    def test_rejects_duplicate_screenshot_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = write_capture(root, 1, (10, 20, 30))
            second = write_capture(
                root, 2, (40, 50, 60),
                screenshot_bytes_override=first["screenshot_bytes"],
            )
            manifest = {
                "schema_version": 1,
                "captures": [
                    {key: first[key] for key in ("dataset", "detection", "screenshot")},
                    {key: second[key] for key in ("dataset", "detection", "screenshot")},
                ],
            }
            with self.assertRaisesRegex(ValueError, "repeats an identical source screenshot"):
                evaluate_manifest(manifest, base_dir=root)

    def test_rejects_duplicate_capture_session_ids(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = write_capture(root, 1, (10, 20, 30), session_id="same-session")
            second = write_capture(root, 2, (40, 50, 60), session_id="same-session")
            manifest = {
                "schema_version": 1,
                "captures": [
                    {key: first[key] for key in ("dataset", "detection", "screenshot")},
                    {key: second[key] for key in ("dataset", "detection", "screenshot")},
                ],
            }
            with self.assertRaisesRegex(ValueError, "Duplicate capture session_id"):
                evaluate_manifest(manifest, base_dir=root)

    def test_rejects_same_capture_entry_listed_twice(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = write_capture(root, 1, (10, 20, 30))
            entry = {key: first[key] for key in ("dataset", "detection", "screenshot")}
            manifest = {"schema_version": 1, "captures": [entry, entry]}
            with self.assertRaisesRegex(ValueError, "Duplicate capture session_id"):
                evaluate_manifest(manifest, base_dir=root)

    def test_rejects_missing_manifest_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = {
                "schema_version": 1,
                "captures": [{
                    "dataset": "missing-labels.json",
                    "detection": "missing-detection.json",
                    "screenshot": "missing-screenshot.png",
                }],
            }
            with self.assertRaisesRegex(ValueError, "unreadable source artifact"):
                evaluate_manifest(manifest, base_dir=directory)

    def test_rejects_empty_or_invalid_manifest(self):
        for manifest in (
            None,
            [],
            {"schema_version": 2, "captures": []},
            {"schema_version": 1, "captures": []},
        ):
            with self.subTest(manifest=manifest):
                with self.assertRaises(ValueError):
                    evaluate_manifest(manifest)

    def test_rejects_non_object_capture_entry(self):
        with self.assertRaisesRegex(ValueError, "capture 0 must be an object"):
            evaluate_manifest({"schema_version": 1, "captures": [None]})


if __name__ == "__main__":
    unittest.main(verbosity=2)
