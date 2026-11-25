#!/usr/bin/env python3
"""Aggregate human-reviewed shooter detector evaluation across captures."""
import argparse
from collections import Counter
import json
from strict_json import strict_json_loads
from pathlib import Path

from shooter_observation_evaluation import (
    evaluate_dataset,
    validate_dataset,
    verify_source_artifacts,
)
from shooter_review_coverage import (
    aggregate_coverage_profiles,
    coverage_profile,
    review_follow_up,
)


def _metric(pairs):
    if not pairs:
        return {
            "support": 0,
            "correct_count": 0,
            "accuracy": None,
            "confusion_matrix": {},
        }
    labels = sorted(
        {actual for actual, _ in pairs}
        | {predicted for _, predicted in pairs}
    )
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


def evaluate_manifest(manifest, base_dir="."):
    if not isinstance(manifest, dict):
        raise ValueError("Manifest must be a JSON object")
    if type(manifest.get("schema_version")) is not int or manifest["schema_version"] != 1:
        raise ValueError("Manifest schema_version must be 1")
    captures = manifest.get("captures")
    if not isinstance(captures, list) or not captures:
        raise ValueError("Manifest captures must be a non-empty list")
    if len(captures) > 1000:
        raise ValueError("Manifest may contain at most 1,000 captures")

    root = Path(base_dir)
    session_ids = set()
    detection_hashes = set()
    screenshot_hashes = set()
    capture_summaries = []
    sample_results = []
    coverage_profiles = []
    visibility_pairs = []
    position_pairs = []
    colour_pairs = []
    ammunition_reviewed = []
    total_samples = 0
    total_confirmed = 0
    total_ambiguous = 0

    for index, entry in enumerate(captures):
        if not isinstance(entry, dict):
            raise ValueError(f"Manifest capture {index} must be an object")
        paths = {}
        for field in ("dataset", "detection", "screenshot"):
            value = entry.get(field)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(
                    f"Manifest capture {index} must supply a non-empty {field} path"
                )
            path = Path(value).expanduser()
            paths[field] = path if path.is_absolute() else root / path

        try:
            dataset = strict_json_loads(paths["dataset"].read_text(encoding="utf-8"))
            detection_bytes = paths["detection"].read_bytes()
            screenshot_bytes = paths["screenshot"].read_bytes()
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(
                f"Manifest capture {index} has an unreadable source artifact: {exc}"
            ) from exc

        validate_dataset(dataset)
        verification = verify_source_artifacts(
            dataset, detection_bytes, screenshot_bytes
        )
        report = evaluate_dataset(dataset)
        coverage_profile = coverage_profile(dataset)
        coverage_profiles.append(coverage_profile)
        provenance = dataset["capture_provenance"]
        session_id = provenance["capture_session_id"]
        detection_hash = verification["source_detection_sha256"]
        screenshot_hash = verification["source_screenshot_sha256"]

        if session_id in session_ids:
            raise ValueError(f"Duplicate capture session_id in manifest: {session_id}")
        if detection_hash in detection_hashes:
            raise ValueError("Manifest repeats an identical source detector JSON")
        if screenshot_hash in screenshot_hashes:
            raise ValueError("Manifest repeats an identical source screenshot")
        session_ids.add(session_id)
        detection_hashes.add(detection_hash)
        screenshot_hashes.add(screenshot_hash)

        metrics = report["metrics"]
        confirmed_results = report["sample_results"]
        total_samples += report["sample_count"]
        total_confirmed += report["confirmed_sample_count"]
        total_ambiguous += report["ambiguous_sample_count"]

        for item in confirmed_results:
            visibility_pairs.append((
                item["reviewed_visibility"], item["detected_visibility"]
            ))
            if item["reviewed_position"] is not None:
                human = item["reviewed_position"]
                detected = item["detected_position"]
                position_pairs.append((
                    f"r{human[0]}c{human[1]}",
                    f"r{detected[0]}c{detected[1]}",
                ))
            if item["reviewed_colour"] is not None:
                colour_pairs.append((
                    item["reviewed_colour"], item["detected_colour"]
                ))
            if item["reviewed_ammunition"] is not None:
                ammunition_reviewed.append({
                    "actual": item["reviewed_ammunition"],
                    "predicted": item["detected_ammunition"],
                })
            sample_results.append({
                "capture_session_id": session_id,
                **item,
            })

        capture_summaries.append({
            "capture_session_id": session_id,
            "source_detection_sha256": detection_hash,
            "source_screenshot_sha256": screenshot_hash,
            "sample_count": report["sample_count"],
            "confirmed_sample_count": report["confirmed_sample_count"],
            "ambiguous_sample_count": report["ambiguous_sample_count"],
            "metrics": metrics,
            "coverage_profile": coverage_profile,
            "review_follow_up": review_follow_up(coverage_profile),
            "source_artifacts_verified": True,
        })

    correct_ammunition = sum(
        item["actual"] == item["predicted"] for item in ammunition_reviewed
    )
    detected_ammunition = [
        item for item in ammunition_reviewed if item["predicted"] is not None
    ]
    absolute_errors = [
        abs(item["actual"] - item["predicted"])
        for item in detected_ammunition
    ]
    aggregate_coverage_profile = aggregate_coverage_profiles(coverage_profiles)
    return {
        "schema_version": 1,
        "evaluator": "shooter_batch_evaluation",
        "capture_count": len(capture_summaries),
        "sample_count": total_samples,
        "confirmed_sample_count": total_confirmed,
        "ambiguous_sample_count": total_ambiguous,
        "metrics": {
            "visibility": _metric(visibility_pairs),
            "slot_position_alignment": _metric(position_pairs),
            "colour": _metric(colour_pairs),
            "ammunition": {
                "support": len(ammunition_reviewed),
                "exact_match_count": correct_ammunition,
                "exact_match_accuracy": (
                    round(correct_ammunition / len(ammunition_reviewed), 6)
                    if ammunition_reviewed else None
                ),
                "detector_reading_count": len(detected_ammunition),
                "detector_missing_count": (
                    len(ammunition_reviewed) - len(detected_ammunition)
                ),
                "mean_absolute_error_on_detected_readings": (
                    round(sum(absolute_errors) / len(absolute_errors), 6)
                    if absolute_errors else None
                ),
            },
        },
        "captures": capture_summaries,
        "coverage_profile": aggregate_coverage_profile,
        "review_follow_up": review_follow_up(aggregate_coverage_profile),
        "sample_results": sample_results,
        "source_provenance": {
            "all_source_artifacts_verified": True,
            "source_detection_hashes": sorted(detection_hashes),
            "source_screenshot_hashes": sorted(screenshot_hashes),
        },
        "ammunition_ocr_status_counts": dict(Counter(
            item.get("detected_ammunition_status", "NOT_REPORTED")
            for item in sample_results
            if item.get("reviewed_visibility") == "visible"
        )),
        "coverage_adequacy_assessed": False,
        "label_source": "user_supplied",
        "label_truth_independently_verified": False,
        "slot_mapping_independently_verified": False,
        "colour_independently_verified": False,
        "ammunition_independently_verified": False,
        "gameplay_verified": False,
        "game_taps_enabled": False,
        "interpretation": (
            "Aggregate metrics combine only human-confirmed samples from distinct, "
            "source-verified captures. They measure agreement with supplied labels; "
            "they do not independently verify label truth, representativeness, "
            "or gameplay performance."
        ),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Aggregate shooter observation evaluation across reviewed captures"
    )
    parser.add_argument("manifest", help="JSON manifest listing labelled dataset, detector and screenshot paths")
    parser.add_argument("--output", default="data/shooter_batch_evaluation.json")
    args = parser.parse_args()

    manifest_path = Path(args.manifest).expanduser().resolve()
    manifest = strict_json_loads(manifest_path.read_text(encoding="utf-8"))
    report = evaluate_manifest(manifest, base_dir=manifest_path.parent)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(json.dumps(report, indent=2), encoding="utf-8")
    temporary.replace(output)

    print("SLIME AI — MULTI-CAPTURE SHOOTER EVALUATION")
    print("=" * 48)
    print("Verified captures:", report["capture_count"])
    print("Confirmed samples:", report["confirmed_sample_count"])
    print("Ambiguous samples:", report["ambiguous_sample_count"])
    for metric_name in ("visibility", "slot_position_alignment", "colour"):
        metric = report["metrics"][metric_name]
        print(
            metric_name, "accuracy:", metric["accuracy"],
            "support:", metric["support"],
        )
    ammunition = report["metrics"]["ammunition"]
    print("Ammunition exact-match accuracy:", ammunition["exact_match_accuracy"])
    coverage = report["coverage_profile"]
    print(
        "Panel positions with confirmed labels:",
        coverage["panel_positions_with_confirmed_labels"], "/ 12",
    )
    print("Human visibility classes represented:", sum(
        count > 0 for count in coverage["human_visibility_class_support"].values()
    ))
    print("Human visible colour classes represented:", sum(
        count > 0 for count in coverage["human_visible_colour_support"].values()
    ))
    print("Distinct legible ammunition values:", len(
        coverage["human_legible_ammunition_value_support"]
    ))
    follow_up = report["review_follow_up"]
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
    print("Independent label verification: False")
    print("Gameplay verified: False")
    print("Game taps enabled: False")
    print("Report:", output)


if __name__ == "__main__":
    main()
