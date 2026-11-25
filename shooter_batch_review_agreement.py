#!/usr/bin/env python3
"""Aggregate two-reviewer agreement across distinct source-bound captures."""
import argparse
import json
from pathlib import Path

from strict_json import strict_json_loads
from shooter_review_agreement import evaluate_review_agreement


AGREEMENT_FIELDS = (
    "review_status",
    "visibility",
    "position",
    "colour",
    "ammunition_readability",
    "ammunition_exact_value",
)


def _aggregate_metric(metrics):
    support = sum(item["support"] for item in metrics)
    agreement_count = sum(item["agreement_count"] for item in metrics)
    return {
        "support": support,
        "agreement_count": agreement_count,
        "agreement_rate": (
            round(agreement_count / support, 6) if support else None
        ),
        "cohen_kappa": None,
        "cohen_kappa_status": (
            "not_pooled_across_captures"
            if support else "no_eligible_pairs"
        ),
    }


def _aggregate_slot_reports(capture_reports):
    by_slot = {}
    for report in capture_reports:
        for slot_id, slot in report["per_slot_agreement"].items():
            target = by_slot.setdefault(slot_id, {
                "row": slot["row"],
                "column": slot["column"],
                "field_metrics": {field: [] for field in AGREEMENT_FIELDS},
                "review_status_metrics": [],
            })
            if (target["row"], target["column"]) != (
                slot["row"], slot["column"]
            ):
                raise ValueError(
                    f"Detector slot {slot_id} maps to different coordinates across captures"
                )
            for field in AGREEMENT_FIELDS:
                target["field_metrics"][field].append(
                    slot["field_agreement"][field]
                )
    aggregated = {}
    for slot_id, slot in sorted(by_slot.items()):
        aggregated[slot_id] = {
            "row": slot["row"],
            "column": slot["column"],
            "field_agreement": {
                field: _aggregate_metric(metrics)
                for field, metrics in slot["field_metrics"].items()
            },
        }
    return aggregated


def evaluate_agreement_manifest(
    manifest,
    base_dir,
    reviewer_a_id,
    reviewer_b_id,
):
    """Validate and aggregate paired reviews across distinct capture sessions."""
    if not isinstance(manifest, dict) or type(
        manifest.get("schema_version")
    ) is not int or manifest["schema_version"] != 1:
        raise ValueError("Manifest must be an object with schema_version 1")
    captures = manifest.get("captures")
    if not isinstance(captures, list) or not captures:
        raise ValueError("Manifest captures must be a non-empty list")
    if len(captures) > 1000:
        raise ValueError("Manifest may contain at most 1,000 captures")

    root = Path(base_dir)
    session_ids = set()
    screenshot_hashes = set()
    capture_reports = []

    for index, entry in enumerate(captures):
        if not isinstance(entry, dict):
            raise ValueError(f"Manifest capture {index} must be an object")
        paths = {}
        for field in ("reviewer_a_dataset", "reviewer_b_dataset",
                      "detection", "screenshot"):
            value = entry.get(field)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(
                    f"Manifest capture {index} needs a non-empty {field} path"
                )
            path = Path(value).expanduser()
            paths[field] = path if path.is_absolute() else root / path

        try:
            dataset_a = strict_json_loads(
                paths["reviewer_a_dataset"].read_bytes()
            )
            dataset_b = strict_json_loads(
                paths["reviewer_b_dataset"].read_bytes()
            )
            detection_bytes = paths["detection"].read_bytes()
            screenshot_bytes = paths["screenshot"].read_bytes()
        except (OSError, UnicodeDecodeError, ValueError) as exc:
            raise ValueError(
                f"Manifest capture {index} has an unreadable or invalid source artifact: {exc}"
            ) from exc

        report = evaluate_review_agreement(
            dataset_a,
            dataset_b,
            reviewer_a_id,
            reviewer_b_id,
            detection_bytes,
            screenshot_bytes,
        )
        session_id = report["source_provenance"]["capture_session_id"]
        screenshot_hash = report["source_provenance"]["source_screenshot_sha256"]
        if session_id in session_ids:
            raise ValueError(
                f"Manifest repeats capture session_id: {session_id}"
            )
        if screenshot_hash in screenshot_hashes:
            raise ValueError("Manifest repeats an identical source screenshot")
        session_ids.add(session_id)
        screenshot_hashes.add(screenshot_hash)

        capture_reports.append({
            "capture_session_id": session_id,
            "source_screenshot_sha256": screenshot_hash,
            "sample_count": report["sample_count"],
            "both_confirmed_sample_count": report[
                "both_confirmed_sample_count"
            ],
            "one_or_both_ambiguous_sample_count": report[
                "one_or_both_ambiguous_sample_count"
            ],
            "field_agreement": report["field_agreement"],
            "per_slot_agreement": report["per_slot_agreement"],
            "disagreement_count": report["disagreement_count"],
            "disagreements": report["disagreements"],
            "source_artifacts_verified": True,
        })

    aggregate_fields = {
        field: _aggregate_metric([
            capture["field_agreement"][field]
            for capture in capture_reports
        ])
        for field in AGREEMENT_FIELDS
    }
    return {
        "schema_version": 1,
        "evaluator": "shooter_batch_review_agreement",
        "reviewer_a_id": reviewer_a_id,
        "reviewer_b_id": reviewer_b_id,
        "capture_count": len(capture_reports),
        "sample_count": sum(item["sample_count"] for item in capture_reports),
        "both_confirmed_sample_count": sum(
            item["both_confirmed_sample_count"] for item in capture_reports
        ),
        "one_or_both_ambiguous_sample_count": sum(
            item["one_or_both_ambiguous_sample_count"]
            for item in capture_reports
        ),
        "field_agreement": aggregate_fields,
        "per_slot_agreement": _aggregate_slot_reports(capture_reports),
        "disagreement_count": sum(
            item["disagreement_count"] for item in capture_reports
        ),
        "captures": capture_reports,
        "source_provenance": {
            "all_capture_sources_verified": True,
            "distinct_capture_sessions": len(session_ids),
            "distinct_source_screenshots": len(screenshot_hashes),
        },
        "reviewer_independence_verified": False,
        "label_truth_independently_verified": False,
        "gameplay_verified": False,
        "game_taps_enabled": False,
        "interpretation": (
            "Agreement rates pool exact agreement counts and eligible support "
            "across distinct source-verified captures. Cohen's kappa remains "
            "per-capture because pooling kappa values is not statistically "
            "equivalent to calculating kappa from pooled contingency counts. "
            "Reviewer identifiers are not authenticated; agreement does not "
            "establish reviewer independence, label truth, detector accuracy, "
            "or gameplay success."
        ),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Aggregate two-reviewer agreement across distinct captures"
    )
    parser.add_argument("manifest")
    parser.add_argument("--reviewer-a-id", required=True)
    parser.add_argument("--reviewer-b-id", required=True)
    parser.add_argument(
        "--output", default="data/shooter_batch_review_agreement.json"
    )
    args = parser.parse_args()

    manifest_path = Path(args.manifest).expanduser().resolve()
    manifest = strict_json_loads(manifest_path.read_bytes())
    report = evaluate_agreement_manifest(
        manifest,
        manifest_path.parent,
        args.reviewer_a_id,
        args.reviewer_b_id,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(json.dumps(report, indent=2), encoding="utf-8")
    temporary.replace(output)

    print("SLIME AI — MULTI-CAPTURE REVIEW AGREEMENT")
    print("Verified captures:", report["capture_count"])
    print("Total paired samples:", report["sample_count"])
    for field, metric in report["field_agreement"].items():
        print(
            field,
            "agreement:", metric["agreement_rate"],
            "support:", metric["support"],
        )
    print("Disagreeing samples:", report["disagreement_count"])
    print("Reviewer independence verified: False")
    print("Label truth independently verified: False")
    print("Gameplay verified: False")
    print("Game taps enabled: False")
    print("Report:", output)


if __name__ == "__main__":
    main()
