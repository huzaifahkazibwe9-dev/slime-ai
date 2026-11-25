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
from pathlib import Path

from evaluate_visual_review_bundle import evaluate_visual_review_bundle

SCHEMA_VERSION = 1
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
        if not isinstance(screenshot_hash, str) or len(screenshot_hash) != 64:
            raise ValueError(f"Bundle {bundle_id} screenshot hash is invalid")
        if not isinstance(session_id, str) or not session_id:
            raise ValueError(f"Bundle {bundle_id} capture session ID is invalid")
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
            "review_artifacts_sha256": report.get("review_artifacts_sha256", {}),
        })

    board = _aggregate_board(reports)
    shooter = _aggregate_shooter(reports)
    return {
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
