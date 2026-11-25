#!/usr/bin/env python3
"""Aggregate multiple independently verified visual-review bundles.

Each bundle is fully re-evaluated from its own source artifacts. Captures must
have unique screenshot hashes and capture-session IDs. Board-colour and shooter
metrics are aggregated independently because they describe different tasks.
"""
import argparse
from collections import Counter
import hashlib
import json
import math
import re
from pathlib import Path

from evaluate_visual_review_bundle import evaluate_visual_review_bundle
from screenshot_ingestor import COLOUR_LABELS
from prepare_shooter_labels import (
    AMMUNITION_OBSERVATION_STATUSES,
    DETECTOR_COLOURS,
)
from shooter_observation_evaluation import HUMAN_VISIBILITY_LABELS
from capture_provenance import (
    parse_aware_capture_timestamp,
    validate_capture_session_id,
)

SCHEMA_VERSION = 1
SAMPLE_QUALITY_STATUSES = frozenset({
    "DISTINCT_SAMPLE",
    "LOW_CONFIDENCE_SAMPLE",
    "NOT_REPORTED",
})
BUNDLE_FIELDS = (
    "manifest",
    "board_labels",
    "shooter_labels",
    "board_observation",
    "shooter_detection",
    "pixel_audit",
    "source_screenshot",
)


def _sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def _canonical_json_bytes(data):
    return json.dumps(data, indent=2, sort_keys=True).encode("utf-8")


def _is_sha256(value):
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _require_unverified_flag(data, field, context):
    if not isinstance(data, dict) or data.get(field) is not False:
        raise ValueError(f"{context} {field} must remain false")


def _verify_report_bundle_provenance(bundles):
    required_review_hashes = {
        "manifest_json", "board_labels_json", "shooter_labels_json"
    }
    required_source_hashes = {
        "board_observation_json", "shooter_detection_json",
        "source_pixel_audit_json", "source_screenshot",
    }
    seen_ids = set()
    seen_screenshots = set()
    seen_sessions = set()

    for index, bundle in enumerate(bundles):
        context = f"Batch report bundle {index}"
        if not isinstance(bundle, dict):
            raise ValueError(f"{context} must be an object")
        if set(bundle) != {
            "id", "capture_identity", "review_artifacts_sha256",
            "source_artifacts_sha256",
        }:
            raise ValueError(f"{context} fields are invalid")

        bundle_id = bundle.get("id")
        if not isinstance(bundle_id, str) or not bundle_id.strip():
            raise ValueError(f"{context} id is invalid")
        if bundle_id in seen_ids:
            raise ValueError(f"Batch report contains duplicate bundle id: {bundle_id}")
        seen_ids.add(bundle_id)

        identity = bundle.get("capture_identity")
        if not isinstance(identity, dict):
            raise ValueError(f"{context} capture_identity is invalid")
        if set(identity) != {
            "source_screenshot_sha256", "source_screenshot_size",
            "capture_session_id", "captured_at",
        }:
            raise ValueError(f"{context} capture_identity fields are invalid")
        screenshot_hash = identity.get("source_screenshot_sha256")
        session_id = identity.get("capture_session_id")
        captured_at = identity.get("captured_at")
        image_size = identity.get("source_screenshot_size")
        if not _is_sha256(screenshot_hash):
            raise ValueError(f"{context} screenshot hash is invalid")
        if not isinstance(session_id, str) or not session_id.strip():
            raise ValueError(f"{context} capture session ID is invalid")
        try:
            if validate_capture_session_id(session_id) != session_id:
                raise ValueError(f"{context} capture session ID is not canonical")
        except ValueError as exc:
            raise ValueError(f"{context} capture session ID is invalid") from exc
        if not isinstance(captured_at, str) or not captured_at.strip():
            raise ValueError(f"{context} capture timestamp is invalid")
        try:
            parsed_captured_at = parse_aware_capture_timestamp(captured_at)
        except ValueError as exc:
            raise ValueError(
                f"{context} capture timestamp must be ISO-8601 with a UTC offset"
            ) from exc
        if parsed_captured_at != captured_at:
            raise ValueError(f"{context} capture timestamp is not canonical")
        if (
            not isinstance(image_size, list)
            or len(image_size) != 2
            or any(type(value) is not int or value < 1 for value in image_size)
        ):
            raise ValueError(f"{context} screenshot dimensions are invalid")
        if screenshot_hash in seen_screenshots:
            raise ValueError(f"Batch report contains duplicate screenshot: {screenshot_hash}")
        if session_id in seen_sessions:
            raise ValueError(f"Batch report contains duplicate capture session: {session_id}")
        seen_screenshots.add(screenshot_hash)
        seen_sessions.add(session_id)

        for field, expected_keys in (
            ("review_artifacts_sha256", required_review_hashes),
            ("source_artifacts_sha256", required_source_hashes),
        ):
            hashes = bundle.get(field)
            if not isinstance(hashes, dict) or set(hashes) != expected_keys:
                raise ValueError(f"{context} {field} fields are invalid")
            if any(not _is_sha256(value) for value in hashes.values()):
                raise ValueError(f"{context} {field} contains an invalid SHA-256 digest")

        if bundle["source_artifacts_sha256"]["source_screenshot"] != screenshot_hash:
            raise ValueError(
                f"{context} source screenshot hash disagrees with capture identity"
            )


def _require_exact_keys(value, expected, context):
    if not isinstance(value, dict) or set(value) != set(expected):
        raise ValueError(f"{context} fields do not match schema-v1")


def _require_finite_number(value, expected, field):
    if expected is None:
        if value is not None:
            raise ValueError(f"{field} is inconsistent with its sample counts")
        return
    if type(value) is not float or not math.isfinite(value) or value != expected:
        raise ValueError(f"{field} is inconsistent with its sample counts")


def _classification_summary(summary, context):
    _require_exact_keys(
        summary,
        {"support", "correct_count", "accuracy", "confusion_matrix"},
        context,
    )
    support = _nonnegative_count(summary["support"], f"{context}.support")
    correct = _nonnegative_count(
        summary["correct_count"], f"{context}.correct_count"
    )
    matrix = summary["confusion_matrix"]
    if not isinstance(matrix, dict):
        raise ValueError(f"{context}.confusion_matrix must be an object")
    if any(not isinstance(label, str) or not label for label in matrix):
        raise ValueError(f"{context} confusion-matrix labels must be non-empty strings")
    labels = sorted(matrix)
    total = 0
    diagonal = 0
    row_counts = {}
    column_counts = {label: 0 for label in labels}
    for actual in labels:
        row = matrix[actual]
        if not isinstance(row, dict) or set(row) != set(labels):
            raise ValueError(f"{context} confusion matrix must be square")
        row_total = 0
        for predicted in labels:
            count = _nonnegative_count(
                row[predicted], f"{context}.confusion_matrix.{actual}.{predicted}"
            )
            row_total += count
            column_counts[predicted] += count
            if actual == predicted:
                diagonal += count
        row_counts[actual] = row_total
        total += row_total
    if total != support or diagonal != correct:
        raise ValueError(f"{context} confusion matrix disagrees with support or correct_count")
    expected_accuracy = round(correct / support, 6) if support else None
    _require_finite_number(
        summary["accuracy"], expected_accuracy, f"{context}.accuracy"
    )
    return {
        "support": support,
        "correct_count": correct,
        "labels": labels,
        "matrix": matrix,
        "row_counts": row_counts,
        "column_counts": column_counts,
    }


def _verify_per_class_metrics(actual, expected, context):
    _require_exact_keys(actual, expected, context)
    for label, expected_metrics in expected.items():
        metrics = actual[label]
        metric_context = f"{context}.{label}"
        _require_exact_keys(
            metrics,
            {"support", "predicted_count", "precision", "recall", "f1"},
            metric_context,
        )
        for count_field in ("support", "predicted_count"):
            actual_count = _nonnegative_count(
                metrics[count_field], f"{metric_context}.{count_field}"
            )
            if actual_count != expected_metrics[count_field]:
                raise ValueError(
                    f"{metric_context}.{count_field} disagrees with confusion matrix"
                )
        for score_field in ("precision", "recall", "f1"):
            _require_finite_number(
                metrics[score_field],
                expected_metrics[score_field],
                f"{metric_context}.{score_field}",
            )


def _verify_board_summary(board):
    _require_exact_keys(
        board,
        {
            "sample_count", "correct_count", "accuracy", "macro_recall",
            "labels", "confusion_matrix", "per_class", "aggregation",
            "label_source", "label_truth_independently_verified",
        },
        "Board-colour evaluation",
    )
    if board.get("label_source") != "user_supplied":
        raise ValueError("Batch report board-colour evaluation label_source is invalid")
    _require_unverified_flag(
        board, "label_truth_independently_verified", "Board-colour evaluation"
    )
    if board.get("aggregation") != (
        "pooled sample-level counts across independently verified captures"
    ):
        raise ValueError("Board-colour evaluation aggregation description is invalid")

    classification = _classification_summary(
        {
            "support": board["sample_count"],
            "correct_count": board["correct_count"],
            "accuracy": board["accuracy"],
            "confusion_matrix": board["confusion_matrix"],
        },
        "Board-colour evaluation",
    )
    if board["labels"] != classification["labels"]:
        raise ValueError("Board-colour evaluation labels disagree with confusion matrix")
    if not set(classification["labels"]).issubset(set(COLOUR_LABELS)):
        raise ValueError("Board-colour evaluation contains a noncanonical colour label")

    expected_per_class = {}
    recalls = []
    for label in classification["labels"]:
        true_positive = classification["matrix"][label][label]
        support = classification["row_counts"][label]
        predicted_count = classification["column_counts"][label]
        precision = true_positive / predicted_count if predicted_count else 0.0
        recall = true_positive / support if support else 0.0
        f1 = (
            2 * precision * recall / (precision + recall)
            if precision + recall else 0.0
        )
        expected_per_class[label] = {
            "support": support,
            "predicted_count": predicted_count,
            "precision": round(precision, 6),
            "recall": round(recall, 6),
            "f1": round(f1, 6),
        }
        if support:
            recalls.append(recall)
    _verify_per_class_metrics(
        board["per_class"], expected_per_class, "Board-colour per_class"
    )
    expected_macro_recall = (
        round(sum(recalls) / len(recalls), 6) if recalls else 0.0
    )
    _require_finite_number(
        board["macro_recall"], expected_macro_recall,
        "Board-colour macro_recall",
    )


def _verify_shooter_summary(shooter):
    _require_exact_keys(
        shooter,
        {
            "sample_count", "confirmed_sample_count", "ambiguous_sample_count",
            "metrics", "review_coverage", "aggregation", "label_source",
            "label_truth_independently_verified",
            "slot_mapping_independently_verified",
            "colour_independently_verified",
            "ammunition_independently_verified",
        },
        "Shooter evaluation",
    )
    if shooter.get("label_source") != "user_supplied":
        raise ValueError("Batch report shooter evaluation label_source is invalid")
    if shooter.get("aggregation") != (
        "pooled sample-level counts across independently verified captures"
    ):
        raise ValueError("Shooter evaluation aggregation description is invalid")
    for field in (
        "label_truth_independently_verified",
        "slot_mapping_independently_verified",
        "colour_independently_verified",
        "ammunition_independently_verified",
    ):
        _require_unverified_flag(shooter, field, "Shooter evaluation")

    sample_count = _nonnegative_count(
        shooter["sample_count"], "Shooter sample_count"
    )
    confirmed = _nonnegative_count(
        shooter["confirmed_sample_count"], "Shooter confirmed_sample_count"
    )
    ambiguous = _nonnegative_count(
        shooter["ambiguous_sample_count"], "Shooter ambiguous_sample_count"
    )
    if confirmed + ambiguous != sample_count:
        raise ValueError("Shooter confirmed and ambiguous counts do not equal sample_count")

    metrics = shooter["metrics"]
    _require_exact_keys(
        metrics,
        {"visibility", "slot_position_alignment", "colour", "ammunition"},
        "Shooter metrics",
    )
    visibility = _classification_summary(metrics["visibility"], "Shooter visibility")
    position = _classification_summary(
        metrics["slot_position_alignment"], "Shooter slot-position alignment"
    )
    colour = _classification_summary(metrics["colour"], "Shooter colour")
    if visibility["support"] != confirmed:
        raise ValueError("Shooter visibility support does not equal confirmed sample count")
    if position["support"] > confirmed or colour["support"] > confirmed:
        raise ValueError("Shooter metric support exceeds confirmed sample count")
    if not set(visibility["labels"]).issubset(set(HUMAN_VISIBILITY_LABELS)):
        raise ValueError("Shooter visibility metrics contain an unknown visibility label")
    for label in position["labels"]:
        match = re.fullmatch(r"r([0-9]+)c([0-9]+)", label)
        if match is None:
            raise ValueError("Shooter position metrics contain an invalid coordinate label")
        row, column = (int(value) for value in match.groups())
        if label != f"r{row}c{column}":
            raise ValueError("Shooter position metrics contain a noncanonical coordinate")
        if not (1 <= row <= 3 and 1 <= column <= 4):
            raise ValueError("Shooter position metrics contain an out-of-panel coordinate")
    if not set(colour["labels"]).issubset(set(DETECTOR_COLOURS)):
        raise ValueError("Shooter colour metrics contain a noncanonical colour label")

    ammo = metrics["ammunition"]
    _require_exact_keys(
        ammo,
        {
            "support", "exact_match_count", "exact_match_accuracy",
            "detector_reading_count", "detector_missing_count",
            "mean_absolute_error_on_detected_readings",
        },
        "Shooter ammunition metrics",
    )
    ammo_support = _nonnegative_count(ammo["support"], "Ammunition support")
    exact_matches = _nonnegative_count(
        ammo["exact_match_count"], "Ammunition exact_match_count"
    )
    detected = _nonnegative_count(
        ammo["detector_reading_count"], "Ammunition detector_reading_count"
    )
    missing = _nonnegative_count(
        ammo["detector_missing_count"], "Ammunition detector_missing_count"
    )
    if detected + missing != ammo_support or exact_matches > detected:
        raise ValueError("Shooter ammunition counts are internally inconsistent")
    expected_accuracy = (
        round(exact_matches / ammo_support, 6) if ammo_support else None
    )
    _require_finite_number(
        ammo["exact_match_accuracy"], expected_accuracy,
        "Shooter ammunition exact-match accuracy",
    )
    mae = ammo["mean_absolute_error_on_detected_readings"]
    if detected == 0:
        if mae is not None:
            raise ValueError("Shooter ammunition MAE must be null without detector readings")
    elif (
        type(mae) is not float
        or not math.isfinite(mae)
        or mae < 0
    ):
        raise ValueError("Shooter ammunition MAE must be finite and non-negative")
    else:
        minimum_mae = round((detected - exact_matches) / detected, 6)
        if mae < minimum_mae:
            raise ValueError(
                "Shooter ammunition MAE is below the minimum implied by "
                "its exact-match count"
            )
        if exact_matches == detected and mae != 0.0:
            raise ValueError(
                "Shooter ammunition MAE must be zero when all detector readings match"
            )
        implied_error_total = mae * detected
        if not math.isfinite(implied_error_total):
            raise ValueError("Shooter ammunition MAE implies an invalid total error")
        nearest_error_total = round(implied_error_total)
        if round(nearest_error_total / detected, 6) != mae:
            raise ValueError(
                "Shooter ammunition MAE is incompatible with an integer total error"
            )

    coverage = shooter["review_coverage"]
    _require_exact_keys(
        coverage,
        {
            "confirmed_visibility_counts",
            "visible_samples_with_human_colour",
            "visible_samples_with_legible_human_ammunition",
            "visible_sample_quality_status_counts",
            "visible_ammunition_ocr_status_counts",
            "coverage_adequacy_assessed",
        },
        "Shooter review coverage",
    )
    if coverage["coverage_adequacy_assessed"] is not False:
        raise ValueError("Shooter coverage_adequacy_assessed must remain false")
    visibility_counts = _count_dictionary(
        coverage["confirmed_visibility_counts"], "confirmed_visibility_counts"
    )
    quality_counts = _count_dictionary(
        coverage["visible_sample_quality_status_counts"],
        "visible_sample_quality_status_counts",
    )
    ammo_status_counts = _count_dictionary(
        coverage["visible_ammunition_ocr_status_counts"],
        "visible_ammunition_ocr_status_counts",
    )
    if not set(visibility_counts).issubset(set(HUMAN_VISIBILITY_LABELS)):
        raise ValueError("Shooter visibility coverage contains an unknown visibility label")
    if not set(quality_counts).issubset(SAMPLE_QUALITY_STATUSES):
        raise ValueError("Shooter sample-quality coverage contains an unknown status")
    if not set(ammo_status_counts).issubset(set(AMMUNITION_OBSERVATION_STATUSES)):
        raise ValueError("Shooter ammunition coverage contains an unknown OCR status")
    if sum(visibility_counts.values()) != confirmed:
        raise ValueError("Shooter visibility coverage counts do not equal confirmed samples")
    positive_visibility_row_counts = {
        label: count for label, count in visibility["row_counts"].items() if count > 0
    }
    if visibility_counts != positive_visibility_row_counts:
        raise ValueError(
            "Shooter visibility coverage counts disagree with visibility "
            "confusion-matrix row totals"
        )
    visible_count = visibility_counts.get("visible", 0)
    if sum(quality_counts.values()) != visible_count:
        raise ValueError("Shooter sample-quality coverage does not equal visible samples")
    if sum(ammo_status_counts.values()) != visible_count:
        raise ValueError("Shooter ammunition-status coverage does not equal visible samples")

    human_colour_count = _nonnegative_count(
        coverage["visible_samples_with_human_colour"],
        "visible_samples_with_human_colour",
    )
    human_ammo_count = _nonnegative_count(
        coverage["visible_samples_with_legible_human_ammunition"],
        "visible_samples_with_legible_human_ammunition",
    )
    if human_colour_count != colour["support"] or human_colour_count != visible_count:
        raise ValueError("Shooter human-colour coverage disagrees with colour support")
    if human_ammo_count != ammo_support or human_ammo_count > visible_count:
        raise ValueError("Shooter human-ammunition coverage disagrees with ammunition support")


def verify_batch_report(report):
    """Verify the self-digest and basic structure of a saved batch report."""
    if not isinstance(report, dict):
        raise ValueError("Batch evaluation report must be a JSON object")
    if type(report.get("schema_version")) is not int or report["schema_version"] != SCHEMA_VERSION:
        raise ValueError("Batch evaluation report schema_version is unsupported")
    if report.get("evaluator") != "evaluate_visual_review_batch":
        raise ValueError("Batch evaluation report evaluator identity is invalid")
    required_report_fields = {
        "schema_version", "evaluator", "batch_sha256", "bundle_count", "bundles",
        "board_colour_evaluation", "shooter_observation_evaluation",
        "interpretation", "label_truth_independently_verified",
        "calibration_alignment_verified", "gameplay_verified", "game_taps_enabled",
        "evaluation_sha256",
    }
    if set(report) != required_report_fields:
        raise ValueError("Batch evaluation report fields do not match schema-v1")
    digest = report.get("evaluation_sha256")
    if (not isinstance(digest, str) or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)):
        raise ValueError("Batch evaluation report evaluation_sha256 is invalid")
    unsigned = {key: value for key, value in report.items() if key != "evaluation_sha256"}
    if _sha256(_canonical_json_bytes(unsigned)) != digest:
        raise ValueError("Batch evaluation report content does not match evaluation_sha256")
    if not _is_sha256(report.get("batch_sha256")):
        raise ValueError("Batch evaluation report batch_sha256 is invalid")
    expected_interpretation = (
        "Metrics pool reviewed samples only after each capture bundle passes its own "
        "source-bound verification. Board-colour and shooter-observation metrics remain "
        "separate. The pooled results measure agreement with user-supplied labels; they "
        "do not independently verify label truth, calibration alignment, game semantics, "
        "or gameplay performance."
    )
    if report.get("interpretation") != expected_interpretation:
        raise ValueError("Batch evaluation report interpretation is invalid")
    if type(report.get("bundle_count")) is not int or report["bundle_count"] < 2:
        raise ValueError("Batch evaluation report bundle_count is invalid")
    bundles = report.get("bundles")
    if not isinstance(bundles, list) or len(bundles) != report["bundle_count"]:
        raise ValueError("Batch evaluation report bundles do not match bundle_count")
    _verify_report_bundle_provenance(bundles)

    for field in (
        "label_truth_independently_verified",
        "calibration_alignment_verified",
        "gameplay_verified",
        "game_taps_enabled",
    ):
        _require_unverified_flag(report, field, "Batch report")

    _verify_board_summary(report.get("board_colour_evaluation"))
    _verify_shooter_summary(report.get("shooter_observation_evaluation"))
    return True


def _read_batch(path):
    try:
        raw = Path(path).read_bytes()
    except OSError as exc:
        raise ValueError("Batch manifest is missing or unreadable") from exc
    try:
        data = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Batch manifest is not valid UTF-8 JSON") from exc
    if not isinstance(data, dict):
        raise ValueError("Batch manifest must be a JSON object")
    if type(data.get("schema_version")) is not int or data["schema_version"] != SCHEMA_VERSION:
        raise ValueError(f"Batch schema_version must be {SCHEMA_VERSION}")
    bundles = data.get("bundles")
    if not isinstance(bundles, list) or len(bundles) < 2:
        raise ValueError("Batch must contain at least two review bundles")
    return data, raw, Path(path).resolve().parent


def _resolve_bundle_path(base, value, bundle_id, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Bundle {bundle_id} {field} path must be a non-empty string")
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts or "\\" in value:
        raise ValueError(f"Bundle {bundle_id} {field} path must stay inside the batch directory")
    resolved = (base / relative).resolve()
    try:
        resolved.relative_to(base.resolve())
    except ValueError as exc:
        raise ValueError(
            f"Bundle {bundle_id} {field} path escapes the batch directory"
        ) from exc
    return resolved


def _validate_pairs(pairs, description):
    for actual, predicted in pairs:
        if not isinstance(actual, str) or not actual:
            raise ValueError(f"{description} actual labels must be non-empty strings")
        if not isinstance(predicted, str) or not predicted:
            raise ValueError(f"{description} predicted labels must be non-empty strings")
    return pairs


def _classification_metrics(pairs):
    _validate_pairs(pairs, "Classification")
    if not pairs:
        return {
            "support": 0,
            "correct_count": 0,
            "accuracy": None,
            "confusion_matrix": {},
        }
    labels = sorted({actual for actual, _ in pairs} | {predicted for _, predicted in pairs})
    matrix = {
        actual: {
            predicted: sum(
                1 for pair_actual, pair_predicted in pairs
                if pair_actual == actual and pair_predicted == predicted
            )
            for predicted in labels
        }
        for actual in labels
    }
    correct = sum(actual == predicted for actual, predicted in pairs)
    return {
        "support": len(pairs),
        "correct_count": correct,
        "accuracy": round(correct / len(pairs), 6),
        "confusion_matrix": matrix,
    }


def _nonnegative_count(value, field):
    if type(value) is not int or value < 0:
        raise ValueError(f"{field} must be a non-negative integer")
    return value


def _aggregate_board(reports):
    pairs = []
    for report in reports:
        evaluation = report.get("board_colour_evaluation")
        if not isinstance(evaluation, dict):
            raise ValueError("A verified bundle is missing board-colour metrics")
        results = evaluation.get("sample_results")
        if not isinstance(results, list):
            raise ValueError("Board-colour sample_results must be a list")
        expected = _nonnegative_count(evaluation.get("sample_count"), "Board sample_count")
        if expected != len(results):
            raise ValueError("Board sample_count does not match sample_results")
        for item in results:
            if not isinstance(item, dict):
                raise ValueError("Board sample result must be an object")
            pairs.append((item.get("actual"), item.get("predicted")))

    metrics = _classification_metrics(pairs)
    matrix = metrics["confusion_matrix"]
    per_class = {}
    recalls = []
    for label in sorted(matrix):
        true_positive = matrix[label][label]
        support = sum(matrix[label].values())
        predicted_count = sum(matrix[actual][label] for actual in matrix)
        precision = true_positive / predicted_count if predicted_count else 0.0
        recall = true_positive / support if support else 0.0
        f1 = (
            2 * precision * recall / (precision + recall)
            if precision + recall else 0.0
        )
        per_class[label] = {
            "support": support,
            "predicted_count": predicted_count,
            "precision": round(precision, 6),
            "recall": round(recall, 6),
            "f1": round(f1, 6),
        }
        if support:
            recalls.append(recall)
    return {
        "sample_count": metrics["support"],
        "correct_count": metrics["correct_count"],
        "accuracy": metrics["accuracy"],
        "macro_recall": round(sum(recalls) / len(recalls), 6) if recalls else 0.0,
        "labels": sorted(matrix),
        "confusion_matrix": matrix,
        "per_class": per_class,
        "aggregation": "pooled sample-level counts across independently verified captures",
        "label_source": "user_supplied",
        "label_truth_independently_verified": False,
    }


def _count_dictionary(value, field):
    if not isinstance(value, dict):
        raise ValueError(f"{field} must be an object")
    result = {}
    for key, count in value.items():
        if not isinstance(key, str) or not key:
            raise ValueError(f"{field} keys must be non-empty strings")
        result[key] = _nonnegative_count(count, f"{field}.{key}")
        if result[key] == 0:
            raise ValueError(f"{field}.{key} must be a positive count")
    return result


def _aggregate_shooter(reports):
    visibility_pairs = []
    position_pairs = []
    colour_pairs = []
    ammo_reviewed = 0
    ammo_correct = 0
    ammo_detected = 0
    absolute_errors = []
    sample_count = 0
    confirmed_count = 0
    ambiguous_count = 0
    visibility_counts = Counter()
    quality_counts = Counter()
    ammo_status_counts = Counter()
    visible_with_colour = 0

    for report in reports:
        evaluation = report.get("shooter_observation_evaluation")
        if not isinstance(evaluation, dict):
            raise ValueError("A verified bundle is missing shooter-observation metrics")
        total = _nonnegative_count(evaluation.get("sample_count"), "Shooter sample_count")
        confirmed = _nonnegative_count(
            evaluation.get("confirmed_sample_count"), "Shooter confirmed_sample_count"
        )
        ambiguous = _nonnegative_count(
            evaluation.get("ambiguous_sample_count"), "Shooter ambiguous_sample_count"
        )
        if confirmed + ambiguous != total:
            raise ValueError("Shooter confirmed and ambiguous counts do not equal sample_count")
        results = evaluation.get("sample_results")
        if not isinstance(results, list) or len(results) != confirmed:
            raise ValueError("Shooter sample_results must contain exactly the confirmed samples")
        coverage = evaluation.get("review_coverage")
        if not isinstance(coverage, dict):
            raise ValueError("Shooter review_coverage must be an object")

        sample_count += total
        confirmed_count += confirmed
        ambiguous_count += ambiguous
        visibility_counts.update(_count_dictionary(
            coverage.get("confirmed_visibility_counts"), "confirmed_visibility_counts"
        ))
        quality_counts.update(_count_dictionary(
            coverage.get("visible_sample_quality_status_counts"),
            "visible_sample_quality_status_counts",
        ))
        ammo_status_counts.update(_count_dictionary(
            coverage.get("visible_ammunition_ocr_status_counts"),
            "visible_ammunition_ocr_status_counts",
        ))

        for item in results:
            if not isinstance(item, dict):
                raise ValueError("Shooter sample result must be an object")
            visibility_pairs.append((
                item.get("reviewed_visibility"), item.get("detected_visibility")
            ))
            reviewed_position = item.get("reviewed_position")
            if reviewed_position is not None:
                detected_position = item.get("detected_position")
                if (not isinstance(reviewed_position, list) or len(reviewed_position) != 2
                        or not isinstance(detected_position, list) or len(detected_position) != 2):
                    raise ValueError("Shooter position sample results must be coordinate pairs")
                position_pairs.append((
                    f"r{reviewed_position[0]}c{reviewed_position[1]}",
                    f"r{detected_position[0]}c{detected_position[1]}",
                ))
            if item.get("reviewed_colour") is not None:
                visible_with_colour += 1
                colour_pairs.append((
                    item.get("reviewed_colour"), item.get("detected_colour")
                ))
            reviewed_ammo = item.get("reviewed_ammunition")
            if reviewed_ammo is not None:
                _nonnegative_count(reviewed_ammo, "reviewed_ammunition")
                ammo_reviewed += 1
                detected_ammo = item.get("detected_ammunition")
                if detected_ammo is not None:
                    _nonnegative_count(detected_ammo, "detected_ammunition")
                    ammo_detected += 1
                    absolute_errors.append(abs(detected_ammo - reviewed_ammo))
                if type(item.get("ammunition_correct")) is not bool:
                    raise ValueError("Reviewed ammunition samples require a boolean correctness result")
                expected_correct = (
                    detected_ammo is not None and detected_ammo == reviewed_ammo
                )
                if item["ammunition_correct"] is not expected_correct:
                    raise ValueError(
                        "Reviewed ammunition correctness disagrees with the "
                        "detected and reviewed ammunition values"
                    )
                ammo_correct += item["ammunition_correct"]

    return {
        "sample_count": sample_count,
        "confirmed_sample_count": confirmed_count,
        "ambiguous_sample_count": ambiguous_count,
        "metrics": {
            "visibility": _classification_metrics(visibility_pairs),
            "slot_position_alignment": _classification_metrics(position_pairs),
            "colour": _classification_metrics(colour_pairs),
            "ammunition": {
                "support": ammo_reviewed,
                "exact_match_count": ammo_correct,
                "exact_match_accuracy": (
                    round(ammo_correct / ammo_reviewed, 6) if ammo_reviewed else None
                ),
                "detector_reading_count": ammo_detected,
                "detector_missing_count": ammo_reviewed - ammo_detected,
                "mean_absolute_error_on_detected_readings": (
                    round(sum(absolute_errors) / len(absolute_errors), 6)
                    if absolute_errors else None
                ),
            },
        },
        "review_coverage": {
            "confirmed_visibility_counts": dict(sorted(visibility_counts.items())),
            "visible_samples_with_human_colour": visible_with_colour,
            "visible_samples_with_legible_human_ammunition": ammo_reviewed,
            "visible_sample_quality_status_counts": dict(sorted(quality_counts.items())),
            "visible_ammunition_ocr_status_counts": dict(sorted(ammo_status_counts.items())),
            "coverage_adequacy_assessed": False,
        },
        "aggregation": "pooled sample-level counts across independently verified captures",
        "label_source": "user_supplied",
        "label_truth_independently_verified": False,
        "slot_mapping_independently_verified": False,
        "colour_independently_verified": False,
        "ammunition_independently_verified": False,
    }


def evaluate_batch(batch_path):
    """Re-evaluate all bundles, reject duplicate captures, and pool separate metrics."""
    batch, batch_bytes, base = _read_batch(batch_path)
    seen_ids = set()
    seen_screenshots = set()
    seen_sessions = set()
    reports = []
    bundle_summaries = []

    # Reject duplicate or malformed IDs before evaluating any source artifacts.
    declared_ids = set()
    for index, entry in enumerate(batch["bundles"]):
        if not isinstance(entry, dict):
            raise ValueError(f"Batch bundle {index} must be an object")
        bundle_id = entry.get("id")
        if not isinstance(bundle_id, str) or not bundle_id.strip():
            raise ValueError(f"Batch bundle {index} id must be a non-empty string")
        if bundle_id in declared_ids:
            raise ValueError(f"Duplicate bundle id: {bundle_id}")
        declared_ids.add(bundle_id)

    for index, entry in enumerate(batch["bundles"]):
        if not isinstance(entry, dict):
            raise ValueError(f"Batch bundle {index} must be an object")
        bundle_id = entry.get("id")
        if not isinstance(bundle_id, str) or not bundle_id.strip():
            raise ValueError(f"Batch bundle {index} id must be a non-empty string")
        if bundle_id in seen_ids:
            raise ValueError(f"Duplicate bundle id: {bundle_id}")
        seen_ids.add(bundle_id)
        missing = [field for field in BUNDLE_FIELDS if field not in entry]
        extra = sorted(set(entry) - {"id", *BUNDLE_FIELDS})
        if missing or extra:
            raise ValueError(
                f"Bundle {bundle_id} fields invalid; missing={missing}, extra={extra}"
            )
        paths = [
            _resolve_bundle_path(base, entry[field], bundle_id, field)
            for field in BUNDLE_FIELDS
        ]
        report = evaluate_visual_review_bundle(*paths)
        if not isinstance(report, dict) or report.get("review_bundle_verified") is not True:
            raise ValueError(f"Bundle {bundle_id} did not return a verified evaluation")
        identity = report.get("capture_identity")
        if not isinstance(identity, dict):
            raise ValueError(f"Bundle {bundle_id} is missing capture identity")
        screenshot_hash = identity.get("source_screenshot_sha256")
        session_id = identity.get("capture_session_id")
        captured_at = identity.get("captured_at")
        image_size = identity.get("source_screenshot_size")
        if (not isinstance(screenshot_hash, str) or len(screenshot_hash) != 64
                or any(character not in "0123456789abcdef" for character in screenshot_hash)):
            raise ValueError(f"Bundle {bundle_id} screenshot hash is invalid")
        if not isinstance(session_id, str) or not session_id.strip():
            raise ValueError(f"Bundle {bundle_id} capture session ID is invalid")
        if not isinstance(captured_at, str) or not captured_at.strip():
            raise ValueError(f"Bundle {bundle_id} capture timestamp is invalid")
        if (not isinstance(image_size, list) or len(image_size) != 2
                or any(type(value) is not int or value < 1 for value in image_size)):
            raise ValueError(f"Bundle {bundle_id} screenshot dimensions are invalid")
        artifact_hashes = report.get("review_artifacts_sha256")
        if not isinstance(artifact_hashes, dict):
            raise ValueError(f"Bundle {bundle_id} review artifact hashes are missing")
        for artifact_name in ("manifest_json", "board_labels_json", "shooter_labels_json"):
            digest = artifact_hashes.get(artifact_name)
            if (not isinstance(digest, str) or len(digest) != 64
                    or any(character not in "0123456789abcdef" for character in digest)):
                raise ValueError(
                    f"Bundle {bundle_id} {artifact_name} digest is invalid"
                )
        source_hashes = report.get("source_artifacts_sha256")
        if not isinstance(source_hashes, dict):
            raise ValueError(f"Bundle {bundle_id} source artifact hashes are missing")
        for artifact_name in (
            "board_observation_json",
            "shooter_detection_json",
            "source_pixel_audit_json",
            "source_screenshot",
        ):
            digest = source_hashes.get(artifact_name)
            if (not isinstance(digest, str) or len(digest) != 64
                    or any(character not in "0123456789abcdef" for character in digest)):
                raise ValueError(
                    f"Bundle {bundle_id} {artifact_name} source digest is invalid"
                )
        if source_hashes["source_screenshot"] != screenshot_hash:
            raise ValueError(
                f"Bundle {bundle_id} source screenshot hash disagrees with capture identity"
            )
        if screenshot_hash in seen_screenshots:
            raise ValueError(f"Duplicate source screenshot in batch: {screenshot_hash}")
        if session_id in seen_sessions:
            raise ValueError(f"Duplicate capture session in batch: {session_id}")
        seen_screenshots.add(screenshot_hash)
        seen_sessions.add(session_id)
        reports.append(report)
        bundle_summaries.append({
            "id": bundle_id,
            "capture_identity": identity,
            "review_artifacts_sha256": artifact_hashes,
            "source_artifacts_sha256": source_hashes,
        })

    board = _aggregate_board(reports)
    shooter = _aggregate_shooter(reports)
    report = {
        "schema_version": SCHEMA_VERSION,
        "evaluator": "evaluate_visual_review_batch",
        "batch_sha256": _sha256(batch_bytes),
        "bundle_count": len(reports),
        "bundles": bundle_summaries,
        "board_colour_evaluation": board,
        "shooter_observation_evaluation": shooter,
        "interpretation": (
            "Metrics pool reviewed samples only after each capture bundle passes its own "
            "source-bound verification. Board-colour and shooter-observation metrics remain "
            "separate. The pooled results measure agreement with user-supplied labels; they "
            "do not independently verify label truth, calibration alignment, game semantics, "
            "or gameplay performance."
        ),
        "label_truth_independently_verified": False,
        "calibration_alignment_verified": False,
        "gameplay_verified": False,
        "game_taps_enabled": False,
    }
    report["evaluation_sha256"] = _sha256(_canonical_json_bytes(report))
    return report


def main():
    parser = argparse.ArgumentParser(
        description="Aggregate multiple source-verified visual-review bundles"
    )
    parser.add_argument("batch_manifest")
    parser.add_argument("--output", default="data/visual_review_batch_evaluation.json")
    args = parser.parse_args()
    report = evaluate_batch(args.batch_manifest)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(json.dumps(report, indent=2), encoding="utf-8")
    temporary.replace(output)
    print("SLIME AI — VISUAL REVIEW BATCH")
    print("=" * 40)
    print("Verified capture bundles:", report["bundle_count"])
    print("Board-colour samples:", report["board_colour_evaluation"]["sample_count"])
    print("Board-colour agreement:", report["board_colour_evaluation"]["accuracy"])
    print(
        "Shooter confirmed samples:",
        report["shooter_observation_evaluation"]["confirmed_sample_count"],
    )
    print("Label truth independently verified: False")
    print("Gameplay verified: False")
    print("Game taps enabled: False")
    print("Report:", output)


if __name__ == "__main__":
    main()
