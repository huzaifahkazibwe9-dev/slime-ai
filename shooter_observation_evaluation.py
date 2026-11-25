#!/usr/bin/env python3
"""Evaluate shooter-panel observations against explicitly human-reviewed labels.

Scores agreement with supplied human labels only. This module does not assert
that labels are independently verified or that gameplay is correct.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from strict_json import strict_json_loads
import re

from prepare_shooter_labels import (
    AMMUNITION_OBSERVATION_STATUSES,
    DETECTOR_COLOURS,
    DETECTOR_STATUS_TO_VISIBILITY,
    build_template,
)
from shooter_review_coverage import (
    HUMAN_VISIBILITY_LABELS,
    coverage_profile,
    review_follow_up,
)

SCHEMA_VERSION = 1


def _valid_sha256(value):
    return (
        isinstance(value, str)
        and re.fullmatch(r"[0-9a-f]{64}", value) is not None
    )


def _positive_dimensions(value, name):
    if (not isinstance(value, list) or len(value) != 2
            or any(type(item) is not int or item < 1 for item in value)):
        raise ValueError(f"{name} must contain two positive integers")
    return value[:]


def validate_dataset(data):
    if not isinstance(data, dict):
        raise ValueError("Dataset must be a JSON object")
    if type(data.get("schema_version")) is not int or data["schema_version"] != SCHEMA_VERSION:
        raise ValueError(f"schema_version must be {SCHEMA_VERSION}")
    if data.get("labelled_by_user") is not True:
        raise ValueError("Dataset must explicitly set labelled_by_user to true")

    for field in ("source_detection_sha256", "source_screenshot_sha256"):
        if not _valid_sha256(data.get(field)):
            raise ValueError(f"{field} must be a lowercase 64-character SHA-256 digest")

    _positive_dimensions(data.get("source_screenshot_size"), "source_screenshot_size")
    panel_size = _positive_dimensions(data.get("panel_image_size"), "panel_image_size")

    capture = data.get("capture_provenance")
    if not isinstance(capture, dict):
        raise ValueError("capture_provenance must be an object")
    if capture.get("source_sha256") != data["source_screenshot_sha256"]:
        raise ValueError("capture_provenance source hash does not match dataset")
    if not _valid_sha256(capture.get("capture_config_sha256")):
        raise ValueError("capture_provenance capture config hash is invalid")
    if not isinstance(capture.get("capture_session_id"), str) or not capture["capture_session_id"].strip():
        raise ValueError("capture_provenance capture_session_id is invalid")
    if not isinstance(capture.get("captured_at"), str) or not capture["captured_at"].strip():
        raise ValueError("capture_provenance captured_at is invalid")
    bounds = capture.get("panel_bounds")
    if (not isinstance(bounds, list) or len(bounds) != 4
            or any(type(value) is not int for value in bounds)
            or bounds[0] < 0 or bounds[1] < 0
            or bounds[2] <= bounds[0] or bounds[3] <= bounds[1]):
        raise ValueError("capture_provenance panel_bounds are invalid")

    layout = data.get("panel_layout")
    if not isinstance(layout, dict):
        raise ValueError("panel_layout must be an object")
    rows, columns, slot_count = (
        layout.get("rows"), layout.get("columns"), layout.get("slot_count")
    )
    if (type(rows) is not int or type(columns) is not int
            or rows != 3 or columns != 4):
        raise ValueError("This evaluator supports only the calibrated 3-row by 4-column panel")
    if type(slot_count) is not int or slot_count != 12:
        raise ValueError("panel_layout slot_count must be 12 for the calibrated panel")

    quality = data.get("detector_observation_quality")
    if not isinstance(quality, dict):
        raise ValueError("detector_observation_quality must be an object")
    for flag in (
        "colour_independently_verified",
        "ammunition_independently_verified",
        "slot_mapping_independently_verified",
    ):
        if type(quality.get(flag)) is not bool:
            raise ValueError(f"detector_observation_quality.{flag} must be a boolean")
        if quality[flag] is not False:
            raise ValueError(
                f"detector_observation_quality.{flag} cannot be true without a separate evidence path"
            )

    samples = data.get("samples")
    if not isinstance(samples, list) or len(samples) != slot_count:
        raise ValueError("samples must contain exactly one entry for every panel slot")

    seen_ids = set()
    seen_positions = set()
    validated = []
    confirmed_count = 0
    for index, sample in enumerate(samples):
        if not isinstance(sample, dict):
            raise ValueError(f"Sample {index} must be an object")
        detector = sample.get("detector")
        human = sample.get("human")
        if not isinstance(detector, dict) or not isinstance(human, dict):
            raise ValueError(f"Sample {index} detector and human fields must be objects")

        slot_id = detector.get("id")
        row, column = detector.get("row"), detector.get("column")
        if not isinstance(slot_id, str) or not slot_id.strip():
            raise ValueError(f"Sample {index} has an invalid detector id")
        if slot_id in seen_ids:
            raise ValueError(f"Duplicate detector sample id: {slot_id}")
        seen_ids.add(slot_id)
        if (type(row) is not int or type(column) is not int
                or not 1 <= row <= rows or not 1 <= column <= columns):
            raise ValueError(f"Sample {slot_id} has invalid one-based detector row/column")
        position = (row, column)
        if position in seen_positions:
            raise ValueError(f"Duplicate detector sample position: {position}")
        seen_positions.add(position)

        detector_status = detector.get("status")
        if detector_status not in DETECTOR_STATUS_TO_VISIBILITY:
            raise ValueError(f"Sample {slot_id} has an invalid detector status")
        if detector.get("visibility") != DETECTOR_STATUS_TO_VISIBILITY[detector_status]:
            raise ValueError(f"Sample {slot_id} detector visibility conflicts with detector status")
        detected_colour = detector.get("colour")
        if detected_colour not in DETECTOR_COLOURS:
            raise ValueError(f"Sample {slot_id} has an invalid detector colour")
        detected_ammo = detector.get("ammunition")
        if detected_ammo is not None and (
            type(detected_ammo) is not int or detected_ammo < 0
        ):
            raise ValueError(f"Sample {slot_id} has invalid detector ammunition")

        quality_status = detector.get("sample_quality_status")
        if quality_status not in (None, "DISTINCT_SAMPLE", "LOW_CONFIDENCE_SAMPLE"):
            raise ValueError(f"Sample {slot_id} has invalid detector sample-quality status")
        ammo_status = detector.get(
            "ammunition_observation_status", "NOT_REPORTED"
        )
        if ammo_status not in AMMUNITION_OBSERVATION_STATUSES:
            raise ValueError(f"Sample {slot_id} has invalid ammunition observation status")
        if detector.get("ammunition") is not None and ammo_status != "PARSED_EXACT_DIGITS":
            raise ValueError(f"Sample {slot_id} has a value with a non-success OCR status")
        if detector.get("ammunition") is None and ammo_status == "PARSED_EXACT_DIGITS":
            raise ValueError(f"Sample {slot_id} has a success OCR status without a value")
        if detector.get("row") > 1 and ammo_status not in {
            "NOT_ATTEMPTED_UNVERIFIED_SLOT", "NOT_REPORTED"
        }:
            raise ValueError(f"Sample {slot_id} attempted OCR on an unverified slot")
        center = detector.get("screen_center")
        box = detector.get("screen_box")
        screen_sample = detector.get("screen_sample")
        if (not isinstance(center, list) or len(center) != 2
                or any(type(value) is not int for value in center)):
            raise ValueError(f"Sample {slot_id} screen_center is invalid")
        if (not isinstance(screen_sample, list) or len(screen_sample) != 2
                or any(type(value) is not int for value in screen_sample)):
            raise ValueError(f"Sample {slot_id} screen_sample is invalid")
        if (not isinstance(box, list) or len(box) != 4
                or any(type(value) is not int for value in box)
                or not (0 <= box[0] < box[2] <= panel_size[0]
                        and 0 <= box[1] < box[3] <= panel_size[1])):
            raise ValueError(f"Sample {slot_id} screen_box is outside panel dimensions")
        if not all(
            0 <= point[0] < panel_size[0] and 0 <= point[1] < panel_size[1]
            for point in (center, screen_sample)
        ):
            raise ValueError(f"Sample {slot_id} screen coordinates are outside panel dimensions")

        review_status = sample.get("review_status")
        if review_status not in {"confirmed", "ambiguous"}:
            raise ValueError(
                f"Sample {slot_id} must be marked confirmed or ambiguous before evaluation"
            )
        if review_status == "ambiguous":
            validated.append({
                "detector": detector,
                "review_status": review_status,
                "human": human,
            })
            continue

        confirmed_count += 1
        human_visibility = human.get("visibility")
        if human_visibility not in HUMAN_VISIBILITY_LABELS:
            raise ValueError(f"Sample {slot_id} has an invalid human visibility label")

        human_row, human_column = human.get("row"), human.get("column")
        if (human_row is None) != (human_column is None):
            raise ValueError(f"Sample {slot_id} human row/column must both be set or both be null")
        if human_row is not None and (
            type(human_row) is not int or type(human_column) is not int
            or not 1 <= human_row <= rows or not 1 <= human_column <= columns
        ):
            raise ValueError(f"Sample {slot_id} has invalid human one-based row/column")

        human_colour = human.get("colour")
        ammo_readable = human.get("ammunition_readable")
        human_ammo = human.get("ammunition")
        if human_visibility == "visible":
            if human_colour not in DETECTOR_COLOURS:
                raise ValueError(f"Visible sample {slot_id} needs a canonical human colour")
            if type(ammo_readable) is not bool:
                raise ValueError(f"Visible sample {slot_id} needs boolean ammunition_readable")
            if ammo_readable:
                if type(human_ammo) is not int or human_ammo < 0:
                    raise ValueError(
                        f"Visible sample {slot_id} with readable ammunition needs a non-negative integer"
                    )
            elif human_ammo is not None:
                raise ValueError(
                    f"Visible sample {slot_id} with unreadable ammunition must use null"
                )
        else:
            if human_colour not in ("", None):
                raise ValueError(f"Non-visible sample {slot_id} must not have a human colour")
            if ammo_readable is not False or human_ammo is not None:
                raise ValueError(
                    f"Non-visible sample {slot_id} must set ammunition_readable false and ammunition null"
                )

        validated.append({
            "detector": detector,
            "review_status": review_status,
            "human": human,
        })

    if seen_positions != {
        (row, column)
        for row in range(1, rows + 1)
        for column in range(1, columns + 1)
    }:
        raise ValueError("Dataset samples must cover every panel row/column exactly once")
    if confirmed_count < 1:
        raise ValueError("At least one sample must have confirmed human labels")

    return validated


def _metric(pairs):
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


def evaluate_dataset(data):
    samples = validate_dataset(data)
    confirmed = [sample for sample in samples if sample["review_status"] == "confirmed"]
    reviewed_coverage = coverage_profile({"samples": samples})

    visibility_pairs = [
        (sample["human"]["visibility"], sample["detector"]["visibility"])
        for sample in confirmed
    ]
    position_pairs = [
        (
            f"r{sample['human']['row']}c{sample['human']['column']}",
            f"r{sample['detector']['row']}c{sample['detector']['column']}",
        )
        for sample in confirmed
        if sample["human"]["row"] is not None
    ]
    visible = [
        sample for sample in confirmed
        if sample["human"]["visibility"] == "visible"
    ]
    colour_pairs = [
        (sample["human"]["colour"], sample["detector"]["colour"])
        for sample in visible
    ]
    ammo_reviewed = [
        sample for sample in visible
        if sample["human"]["ammunition_readable"] is True
    ]
    ammo_correct = sum(
        sample["detector"]["ammunition"] == sample["human"]["ammunition"]
        for sample in ammo_reviewed
    )
    ammo_detected = [
        sample for sample in ammo_reviewed
        if sample["detector"]["ammunition"] is not None
    ]
    absolute_errors = [
        abs(sample["detector"]["ammunition"] - sample["human"]["ammunition"])
        for sample in ammo_detected
    ]

    quality_counts = Counter(
        sample["detector"]["sample_quality_status"] or "NOT_REPORTED"
        for sample in visible
    )
    ammo_status_counts = Counter(
        sample["detector"].get("ammunition_observation_status", "NOT_REPORTED")
        for sample in visible
    )
    sample_results = []
    for sample in confirmed:
        detector = sample["detector"]
        human = sample["human"]
        sample_results.append({
            "id": detector["id"],
            "reviewed_visibility": human["visibility"],
            "detected_visibility": detector["visibility"],
            "visibility_correct": human["visibility"] == detector["visibility"],
            "reviewed_position": (
                [human["row"], human["column"]]
                if human["row"] is not None else None
            ),
            "detected_position": [detector["row"], detector["column"]],
            "position_correct": (
                human["row"] == detector["row"]
                and human["column"] == detector["column"]
                if human["row"] is not None else None
            ),
            "reviewed_colour": human["colour"] if human["visibility"] == "visible" else None,
            "detected_colour": detector["colour"] if human["visibility"] == "visible" else None,
            "colour_correct": (
                human["colour"] == detector["colour"]
                if human["visibility"] == "visible" else None
            ),
            "reviewed_ammunition": (
                human["ammunition"]
                if human["visibility"] == "visible"
                and human["ammunition_readable"] else None
            ),
            "detected_ammunition": (
                detector["ammunition"] if human["visibility"] == "visible" else None
            ),
            "detected_ammunition_status": detector.get(
                "ammunition_observation_status", "NOT_REPORTED"
            ),
            "ammunition_correct": (
                detector["ammunition"] == human["ammunition"]
                if human["visibility"] == "visible"
                and human["ammunition_readable"] else None
            ),
        })

    return {
        "schema_version": SCHEMA_VERSION,
        "evaluator": "shooter_observation_evaluation",
        "sample_count": len(samples),
        "confirmed_sample_count": len(confirmed),
        "ambiguous_sample_count": len(samples) - len(confirmed),
        "metrics": {
            "visibility": _metric(visibility_pairs),
            "slot_position_alignment": _metric(position_pairs),
            "colour": _metric(colour_pairs),
            "ammunition": {
                "support": len(ammo_reviewed),
                "exact_match_count": ammo_correct,
                "exact_match_accuracy": (
                    round(ammo_correct / len(ammo_reviewed), 6)
                    if ammo_reviewed else None
                ),
                "detector_reading_count": len(ammo_detected),
                "detector_missing_count": len(ammo_reviewed) - len(ammo_detected),
                "mean_absolute_error_on_detected_readings": (
                    round(sum(absolute_errors) / len(absolute_errors), 6)
                    if absolute_errors else None
                ),
            },
        },
        "review_coverage": {
            "confirmed_visibility_counts": dict(Counter(
                sample["human"]["visibility"] for sample in confirmed
            )),
            "visible_samples_with_human_colour": len(colour_pairs),
            "visible_samples_with_legible_human_ammunition": len(ammo_reviewed),
            "visible_sample_quality_status_counts": dict(quality_counts),
            "visible_ammunition_ocr_status_counts": dict(ammo_status_counts),
            "coverage_adequacy_assessed": False,
        },
        "coverage_profile": reviewed_coverage,
        "review_follow_up": review_follow_up(reviewed_coverage),
        "sample_results": sample_results,
        "source_provenance": {
            "source_detection_sha256": data["source_detection_sha256"],
            "source_screenshot_sha256": data["source_screenshot_sha256"],
            "source_detection_hash_checked": False,
            "source_screenshot_hash_checked": False,
            "source_screenshot_dimensions_checked": False,
        },
        "label_source": "user_supplied",
        "label_truth_independently_verified": False,
        "slot_mapping_independently_verified": False,
        "colour_independently_verified": False,
        "ammunition_independently_verified": False,
        "gameplay_verified": False,
        "game_taps_enabled": False,
        "interpretation": (
            "Metrics measure agreement with the supplied human-reviewed labels. "
            "They do not independently prove label correctness, representativeness, "
            "live-game slot alignment, colour truth, OCR reliability, or gameplay success."
        ),
    }


def verify_source_artifacts(data, detection_bytes, screenshot_bytes):
    """Bind a labelled dataset to the exact detector JSON and original screenshot."""
    if not isinstance(detection_bytes, bytes) or not detection_bytes:
        raise ValueError("Exact source detector JSON bytes are required")
    if not isinstance(screenshot_bytes, bytes) or not screenshot_bytes:
        raise ValueError("Exact original screenshot bytes are required")
    actual_detection_hash = hashlib.sha256(detection_bytes).hexdigest()
    if actual_detection_hash != data.get("source_detection_sha256"):
        raise ValueError("Source detector SHA-256 does not match the labelled dataset")
    actual_screenshot_hash = hashlib.sha256(screenshot_bytes).hexdigest()
    if actual_screenshot_hash != data.get("source_screenshot_sha256"):
        raise ValueError("Source screenshot SHA-256 does not match the labelled dataset")

    try:
        detection = strict_json_loads(detection_bytes)
    except (UnicodeDecodeError, ValueError) as exc:
        raise ValueError("Source detector file is not valid JSON") from exc
    expected = build_template(detection, detection_bytes, screenshot_bytes)

    for key in (
        "source_detection_sha256", "source_screenshot_sha256",
        "source_screenshot_size", "panel_image_size", "capture_provenance",
        "panel_layout", "detector_observation_quality",
    ):
        if data.get(key) != expected.get(key):
            raise ValueError(f"Labelled dataset {key} does not match source artifacts")
    samples = data.get("samples")
    expected_samples = expected["samples"]
    if not isinstance(samples, list) or len(samples) != len(expected_samples):
        raise ValueError("Labelled dataset samples do not match source detector")
    for index, (sample, expected_sample) in enumerate(zip(samples, expected_samples)):
        if not isinstance(sample, dict) or sample.get("detector") != expected_sample["detector"]:
            raise ValueError(
                f"Labelled dataset detector snapshot for sample {index} was changed"
            )
    return {
        "source_detection_sha256": actual_detection_hash,
        "source_screenshot_sha256": actual_screenshot_hash,
        "screenshot_dimensions_checked": True,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Evaluate shooter panel readings against human-reviewed labels"
    )
    parser.add_argument("dataset", help="Completed shooter labels JSON template")
    parser.add_argument("--source-detection", required=True)
    parser.add_argument("--source-screenshot", required=True)
    parser.add_argument("--output", default="data/shooter_observation_evaluation.json")
    args = parser.parse_args()

    data = strict_json_loads(Path(args.dataset).read_bytes())
    validate_dataset(data)
    detection_bytes = Path(args.source_detection).read_bytes()
    screenshot_bytes = Path(args.source_screenshot).read_bytes()
    verification = verify_source_artifacts(data, detection_bytes, screenshot_bytes)
    report = evaluate_dataset(data)
    report["source_provenance"]["source_detection_hash_checked"] = True
    report["source_provenance"]["source_screenshot_hash_checked"] = True
    report["source_provenance"]["source_screenshot_dimensions_checked"] = (
        verification["screenshot_dimensions_checked"]
    )

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(json.dumps(report, indent=2), encoding="utf-8")
    temporary.replace(output)

    metrics = report["metrics"]
    print("SLIME AI — HUMAN-LABELLED SHOOTER EVALUATION")
    print("=" * 48)
    print("Confirmed samples:", report["confirmed_sample_count"])
    print("Ambiguous samples:", report["ambiguous_sample_count"])
    for name in ("visibility", "slot_position_alignment", "colour"):
        metric = metrics[name]
        print(f"{name} accuracy:", metric["accuracy"], "support:", metric["support"])
    ammo = metrics["ammunition"]
    print("Ammunition exact-match accuracy:", ammo["exact_match_accuracy"])
    print("Ammunition missing readings:", ammo["detector_missing_count"])
    coverage = report["coverage_profile"]
    follow_up = report["review_follow_up"]
    print("Panel positions with confirmed labels:", (
        coverage["panel_positions_with_confirmed_labels"], "/ 12"
    ))
    print("Panel positions with review follow-up:", len(
        follow_up["panel_review_targets"]
    ))
    print("Visibility classes with zero support:", len(
        follow_up["visibility_classes_with_zero_confirmed_support"]
    ))
    print("Visible colour classes with zero support:", len(
        follow_up["visible_colour_classes_with_zero_confirmed_support"]
    ))
    print("Coverage adequacy assessed: False")
    print("Source detector hash checked: True")
    print("Source screenshot hash checked: True")
    print("Independent label verification: False")
    print("Gameplay verified: False")
    print("Game taps enabled: False")
    print("Report:", output)


if __name__ == "__main__":
    main()
