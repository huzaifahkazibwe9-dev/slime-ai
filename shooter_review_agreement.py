#!/usr/bin/env python3
"""Compare two human reviews of the same source-bound shooter capture.

Agreement is descriptive evidence about reviewer consistency. Reviewer IDs
are caller-supplied labels, not authenticated identities; this tool does not
establish ground truth or enable gameplay.
"""
import argparse
import json
from pathlib import Path

from strict_json import strict_json_loads
from shooter_observation_evaluation import (
    validate_dataset,
    verify_source_artifacts,
)


def _reviewer_id(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty reviewer identifier")
    return value.strip()


def _agreement_summary(left, right):
    if len(left) != len(right):
        raise ValueError("Agreement inputs must have equal lengths")
    support = len(left)
    if not support:
        return {
            "support": 0,
            "agreement_count": 0,
            "agreement_rate": None,
            "cohen_kappa": None,
            "cohen_kappa_status": "no_eligible_pairs",
        }

    agreement_count = sum(a == b for a, b in zip(left, right))
    left_counts = {}
    right_counts = {}
    for value in left:
        left_counts[value] = left_counts.get(value, 0) + 1
    for value in right:
        right_counts[value] = right_counts.get(value, 0) + 1
    labels = set(left_counts) | set(right_counts)
    expected_agreement = sum(
        left_counts.get(label, 0) * right_counts.get(label, 0)
        for label in labels
    ) / (support * support)

    if expected_agreement >= 1.0:
        kappa = None
        kappa_status = "undefined_expected_agreement_is_one"
    else:
        observed_agreement = agreement_count / support
        kappa = round(
            (observed_agreement - expected_agreement)
            / (1.0 - expected_agreement),
            6,
        )
        kappa_status = "computed"

    return {
        "support": support,
        "agreement_count": agreement_count,
        "agreement_rate": round(agreement_count / support, 6),
        "cohen_kappa": kappa,
        "cohen_kappa_status": kappa_status,
    }


def _sample_label(sample, field):
    human = sample["human"]
    if field == "review_status":
        return sample["review_status"]
    if field == "visibility":
        return human["visibility"]
    if field == "position":
        return (
            (human["row"], human["column"])
            if human["row"] is not None else None
        )
    if field == "colour":
        return human["colour"]
    if field == "ammunition_readable":
        return human["ammunition_readable"]
    if field == "ammunition":
        return human["ammunition"]
    raise ValueError(f"Unsupported review field: {field}")


def evaluate_review_agreement(
    dataset_a,
    dataset_b,
    reviewer_a_id,
    reviewer_b_id,
    detection_bytes,
    screenshot_bytes,
):
    """Evaluate agreement between two separately labelled source-bound datasets."""
    reviewer_a_id = _reviewer_id(reviewer_a_id, "reviewer_a_id")
    reviewer_b_id = _reviewer_id(reviewer_b_id, "reviewer_b_id")
    if reviewer_a_id.casefold() == reviewer_b_id.casefold():
        raise ValueError("Reviewer identifiers must be distinct")

    samples_a = validate_dataset(dataset_a)
    samples_b = validate_dataset(dataset_b)
    verification_a = verify_source_artifacts(
        dataset_a, detection_bytes, screenshot_bytes
    )
    verification_b = verify_source_artifacts(
        dataset_b, detection_bytes, screenshot_bytes
    )

    for field in ("source_detection_sha256", "source_screenshot_sha256"):
        if dataset_a[field] != dataset_b[field]:
            raise ValueError(f"Review datasets do not share the same {field}")
    if (
        dataset_a["capture_provenance"]["capture_session_id"]
        != dataset_b["capture_provenance"]["capture_session_id"]
    ):
        raise ValueError("Review datasets do not share the same capture session")

    if len(samples_a) != len(samples_b):
        raise ValueError("Review datasets have different sample counts")
    for index, (sample_a, sample_b) in enumerate(zip(samples_a, samples_b)):
        detector_a = sample_a["detector"]
        detector_b = sample_b["detector"]
        if detector_a != detector_b:
            raise ValueError(
                f"Review datasets have different detector observations at sample {index}"
            )
        if detector_a["id"] != detector_b["id"]:
            raise ValueError(
                f"Review datasets have different detector slot IDs at sample {index}"
            )

    fields = {
        "review_status": ([], []),
        "visibility": ([], []),
        "position": ([], []),
        "colour": ([], []),
        "ammunition_readability": ([], []),
        "ammunition_exact_value": ([], []),
    }
    disagreements = []
    both_confirmed = 0
    both_ambiguous = 0
    one_or_both_ambiguous = 0

    for sample_a, sample_b in zip(samples_a, samples_b):
        sample_id = sample_a["detector"]["id"]
        status_a = sample_a["review_status"]
        status_b = sample_b["review_status"]
        fields["review_status"][0].append(status_a)
        fields["review_status"][1].append(status_b)
        if status_a == "ambiguous" or status_b == "ambiguous":
            one_or_both_ambiguous += 1
        if status_a == status_b == "ambiguous":
            both_ambiguous += 1

        sample_disagreements = []
        if status_a != status_b:
            sample_disagreements.append({
                "field": "review_status",
                "reviewer_a": status_a,
                "reviewer_b": status_b,
            })
        if status_a == "confirmed" and status_b == "confirmed":
            both_confirmed += 1
            for field in ("visibility", "position"):
                value_a = _sample_label(sample_a, field)
                value_b = _sample_label(sample_b, field)
                fields[field][0].append(value_a)
                fields[field][1].append(value_b)
                if value_a != value_b:
                    sample_disagreements.append({
                        "field": field,
                        "reviewer_a": value_a,
                        "reviewer_b": value_b,
                    })

            visible_a = sample_a["human"]["visibility"] == "visible"
            visible_b = sample_b["human"]["visibility"] == "visible"
            if visible_a and visible_b:
                for field in ("colour", "ammunition_readable"):
                    value_a = _sample_label(sample_a, field)
                    value_b = _sample_label(sample_b, field)
                    report_field = (
                        "ammunition_readability"
                        if field == "ammunition_readable" else field
                    )
                    fields[report_field][0].append(value_a)
                    fields[report_field][1].append(value_b)
                    if value_a != value_b:
                        sample_disagreements.append({
                            "field": report_field,
                            "reviewer_a": value_a,
                            "reviewer_b": value_b,
                        })

                readable_a = sample_a["human"]["ammunition_readable"] is True
                readable_b = sample_b["human"]["ammunition_readable"] is True
                if readable_a and readable_b:
                    value_a = _sample_label(sample_a, "ammunition")
                    value_b = _sample_label(sample_b, "ammunition")
                    fields["ammunition_exact_value"][0].append(value_a)
                    fields["ammunition_exact_value"][1].append(value_b)
                    if value_a != value_b:
                        sample_disagreements.append({
                            "field": "ammunition_exact_value",
                            "reviewer_a": value_a,
                            "reviewer_b": value_b,
                        })

        if sample_disagreements:
            disagreements.append({
                "sample_id": sample_id,
                "disagreements": sample_disagreements,
            })

    field_reports = {
        name: _agreement_summary(*pairs)
        for name, pairs in fields.items()
    }
    return {
        "schema_version": 1,
        "evaluator": "shooter_review_agreement",
        "reviewer_a_id": reviewer_a_id,
        "reviewer_b_id": reviewer_b_id,
        "reviewer_ids_distinct": True,
        "sample_count": len(samples_a),
        "both_confirmed_sample_count": both_confirmed,
        "both_ambiguous_sample_count": both_ambiguous,
        "one_or_both_ambiguous_sample_count": one_or_both_ambiguous,
        "field_agreement": field_reports,
        "disagreement_count": len(disagreements),
        "disagreements": disagreements,
        "source_provenance": {
            "capture_session_id": dataset_a["capture_provenance"][
                "capture_session_id"
            ],
            "source_detection_sha256": verification_a[
                "source_detection_sha256"
            ],
            "source_screenshot_sha256": verification_a[
                "source_screenshot_sha256"
            ],
            "source_artifacts_verified_for_both_reviews": True,
            "source_verification_consistent": (
                verification_a == verification_b
            ),
        },
        "reviewer_independence_verified": False,
        "label_truth_independently_verified": False,
        "gameplay_verified": False,
        "game_taps_enabled": False,
        "interpretation": (
            "Agreement measures consistency between the two supplied review "
            "files on the same source-bound capture. Reviewer identifiers are "
            "caller-supplied and are not authenticated. Agreement does not "
            "establish label truth, reviewer independence, detector accuracy, "
            "or gameplay success. Cohen's kappa is omitted when its expected "
            "agreement denominator is zero."
        ),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Compare two human reviews of the same shooter screenshot"
    )
    parser.add_argument("reviewer_a_dataset")
    parser.add_argument("reviewer_b_dataset")
    parser.add_argument("--reviewer-a-id", required=True)
    parser.add_argument("--reviewer-b-id", required=True)
    parser.add_argument("--source-detection", required=True)
    parser.add_argument("--source-screenshot", required=True)
    parser.add_argument(
        "--output", default="data/shooter_review_agreement.json"
    )
    args = parser.parse_args()

    dataset_a = strict_json_loads(
        Path(args.reviewer_a_dataset).read_bytes()
    )
    dataset_b = strict_json_loads(
        Path(args.reviewer_b_dataset).read_bytes()
    )
    detection_bytes = Path(args.source_detection).read_bytes()
    screenshot_bytes = Path(args.source_screenshot).read_bytes()
    report = evaluate_review_agreement(
        dataset_a,
        dataset_b,
        args.reviewer_a_id,
        args.reviewer_b_id,
        detection_bytes,
        screenshot_bytes,
    )

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(json.dumps(report, indent=2), encoding="utf-8")
    temporary.replace(output)

    print("SLIME AI — TWO-REVIEWER AGREEMENT")
    print("=" * 42)
    print("Source artifacts verified for both reviews: True")
    print("Samples reviewed by both:", report["both_confirmed_sample_count"])
    for field, metric in report["field_agreement"].items():
        print(
            field,
            "agreement:", metric["agreement_rate"],
            "support:", metric["support"],
            "Cohen's kappa:", metric["cohen_kappa"],
        )
    print("Disagreeing samples:", report["disagreement_count"])
    print("Reviewer independence verified: False")
    print("Label truth independently verified: False")
    print("Gameplay verified: False")
    print("Game taps enabled: False")
    print("Report:", output)


if __name__ == "__main__":
    main()
