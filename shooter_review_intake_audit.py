#!/usr/bin/env python3
"""Preflight paired shooter-review datasets, including partially completed work.

This audit checks that both reviewers' files remain bound to the exact source
capture and reports label-completion progress. It does not measure agreement,
authenticate reviewers, establish label truth, or enable gameplay.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from prepare_shooter_labels import DETECTOR_COLOURS, build_template
from shooter_review_coverage import HUMAN_VISIBILITY_LABELS
from strict_json import strict_json_loads


def _reviewer_id(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty reviewer identifier")
    value = value.strip()
    if len(value) > 128:
        raise ValueError(f"{label} must be at most 128 characters")
    return value


def _validate_human_label(human, slot_id):
    if not isinstance(human, dict):
        raise ValueError(f"Sample {slot_id} human fields must be an object")
    expected_keys = {
        "visibility", "row", "column", "colour",
        "ammunition_readable", "ammunition",
    }
    if set(human) != expected_keys:
        raise ValueError(f"Sample {slot_id} human fields do not match the review schema")

    visibility = human["visibility"]
    if visibility not in HUMAN_VISIBILITY_LABELS:
        raise ValueError(f"Sample {slot_id} has an invalid human visibility label")

    row, column = human["row"], human["column"]
    if (row is None) != (column is None):
        raise ValueError(f"Sample {slot_id} human row/column must both be set or both be null")
    if row is not None and (
        type(row) is not int or type(column) is not int
        or not 1 <= row <= 3 or not 1 <= column <= 4
    ):
        raise ValueError(f"Sample {slot_id} has invalid human one-based row/column")

    colour = human["colour"]
    ammo_readable = human["ammunition_readable"]
    ammo = human["ammunition"]
    if visibility == "visible":
        if colour not in DETECTOR_COLOURS:
            raise ValueError(f"Visible sample {slot_id} needs a canonical human colour")
        if type(ammo_readable) is not bool:
            raise ValueError(f"Visible sample {slot_id} needs boolean ammunition_readable")
        if ammo_readable:
            if type(ammo) is not int or ammo < 0:
                raise ValueError(
                    f"Visible sample {slot_id} with readable ammunition needs a non-negative integer"
                )
        elif ammo is not None:
            raise ValueError(
                f"Visible sample {slot_id} with unreadable ammunition must use null"
            )
    else:
        if colour not in ("", None):
            raise ValueError(f"Non-visible sample {slot_id} must not have a human colour")
        if ammo_readable is not False or ammo is not None:
            raise ValueError(
                f"Non-visible sample {slot_id} must set ammunition_readable false and ammunition null"
            )


def _dataset_progress(dataset, expected_template, label):
    if not isinstance(dataset, dict):
        raise ValueError(f"{label} must be a JSON object")
    if set(dataset) != set(expected_template):
        raise ValueError(f"{label} top-level fields do not match the review template")
    if type(dataset.get("labelled_by_user")) is not bool:
        raise ValueError(f"{label}.labelled_by_user must be a boolean")

    for field, expected in expected_template.items():
        if field not in {"labelled_by_user", "samples"} and dataset[field] != expected:
            raise ValueError(f"{label} source/template field changed: {field}")

    samples = dataset.get("samples")
    expected_samples = expected_template["samples"]
    if not isinstance(samples, list) or len(samples) != len(expected_samples):
        raise ValueError(f"{label}.samples must contain exactly {len(expected_samples)} panel slots")

    counts = Counter()
    for index, (sample, expected) in enumerate(zip(samples, expected_samples)):
        slot_id = expected["detector"]["id"]
        if not isinstance(sample, dict) or set(sample) != set(expected):
            raise ValueError(f"{label} sample {index} does not match the review schema")
        if sample.get("detector") != expected["detector"]:
            raise ValueError(f"{label} detector snapshot changed for sample {slot_id}")

        status = sample.get("review_status")
        if not isinstance(status, str) or status not in {
            "not_reviewed", "confirmed", "ambiguous"
        }:
            raise ValueError(f"{label} sample {slot_id} has an invalid review_status")
        human = sample.get("human")
        if not isinstance(human, dict) or set(human) != set(expected["human"]):
            raise ValueError(f"{label} sample {slot_id} human fields do not match the template")

        if status == "not_reviewed":
            if human != expected["human"]:
                raise ValueError(
                    f"{label} unreviewed sample {slot_id} contains human labels"
                )
        elif status == "ambiguous":
            if human != expected["human"]:
                raise ValueError(
                    f"{label} ambiguous sample {slot_id} must keep human fields blank"
                )
        else:
            _validate_human_label(human, slot_id)
        counts[status] += 1

    complete = counts["not_reviewed"] == 0
    if dataset["labelled_by_user"] is not complete:
        raise ValueError(
            f"{label}.labelled_by_user must be {str(complete).lower()} "
            "when compared with sample review statuses"
        )

    total = len(samples)
    reviewed = counts["confirmed"] + counts["ambiguous"]
    return {
        "sample_count": total,
        "reviewed_count": reviewed,
        "confirmed_count": counts["confirmed"],
        "ambiguous_count": counts["ambiguous"],
        "not_reviewed_count": counts["not_reviewed"],
        "completion_rate": round(reviewed / total, 6) if total else None,
        "complete": complete,
        "agreement_eligible": counts["confirmed"] >= 1,
        "agreement_eligibility_reason": (
            "at_least_one_confirmed_sample"
            if counts["confirmed"] >= 1
            else "no_confirmed_samples"
        ),
        "labelled_by_user": dataset["labelled_by_user"],
        "dataset_sha256": None,
    }


def _resolve_manifest_path(root, value, index, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            f"Manifest capture {index} needs a non-empty {field} path"
        )
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def audit_review_intake(manifest, base_dir, reviewer_a_id, reviewer_b_id):
    """Audit source binding and completion progress for each paired capture."""
    reviewer_a_id = _reviewer_id(reviewer_a_id, "reviewer_a_id")
    reviewer_b_id = _reviewer_id(reviewer_b_id, "reviewer_b_id")
    if reviewer_a_id.casefold() == reviewer_b_id.casefold():
        raise ValueError("Reviewer identifiers must be distinct")

    if not isinstance(manifest, dict) or set(manifest) != {
        "schema_version", "captures"
    }:
        raise ValueError("Manifest must contain only schema_version and captures")
    if type(manifest.get("schema_version")) is not int or manifest["schema_version"] != 1:
        raise ValueError("Manifest schema_version must be 1")
    captures = manifest.get("captures")
    if not isinstance(captures, list) or not captures:
        raise ValueError("Manifest captures must be a non-empty list")
    if len(captures) > 1000:
        raise ValueError("Manifest may contain at most 1,000 captures")

    root = Path(base_dir).expanduser().resolve()
    used_dataset_paths = set()
    session_ids = set()
    screenshot_hashes = set()
    capture_reports = []
    reviewer_a_totals = Counter()
    reviewer_b_totals = Counter()
    total_samples = 0

    for index, entry in enumerate(captures):
        if not isinstance(entry, dict) or set(entry) != {
            "reviewer_a_dataset", "reviewer_b_dataset", "detection", "screenshot"
        }:
            raise ValueError(
                f"Manifest capture {index} must contain the four paired source paths"
            )
        paths = {
            field: _resolve_manifest_path(root, entry[field], index, field)
            for field in (
                "reviewer_a_dataset", "reviewer_b_dataset",
                "detection", "screenshot",
            )
        }
        if paths["reviewer_a_dataset"] == paths["reviewer_b_dataset"]:
            raise ValueError(
                f"Manifest capture {index} cannot reuse one file for both reviewers"
            )
        for field in ("reviewer_a_dataset", "reviewer_b_dataset"):
            path = paths[field]
            if path in used_dataset_paths:
                raise ValueError(
                    f"Manifest reuses a reviewer dataset file: {path.name}"
                )
            used_dataset_paths.add(path)
        if paths["reviewer_a_dataset"] in {
            paths["detection"], paths["screenshot"]
        } or paths["reviewer_b_dataset"] in {
            paths["detection"], paths["screenshot"]
        }:
            raise ValueError(
                f"Manifest capture {index} reuses a source file as a review dataset"
            )

        try:
            dataset_a_bytes = paths["reviewer_a_dataset"].read_bytes()
            dataset_b_bytes = paths["reviewer_b_dataset"].read_bytes()
            detection_bytes = paths["detection"].read_bytes()
            screenshot_bytes = paths["screenshot"].read_bytes()
            dataset_a = strict_json_loads(dataset_a_bytes)
            dataset_b = strict_json_loads(dataset_b_bytes)
            detection = strict_json_loads(detection_bytes)
        except (OSError, UnicodeDecodeError, ValueError) as exc:
            raise ValueError(
                f"Manifest capture {index} has an unreadable or invalid source artifact: {exc}"
            ) from exc

        try:
            expected = build_template(
                detection, detection_bytes, screenshot_bytes
            )
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"Manifest capture {index} source verification failed: {exc}"
            ) from exc

        progress_a = _dataset_progress(
            dataset_a, expected, f"capture {index} reviewer A"
        )
        progress_b = _dataset_progress(
            dataset_b, expected, f"capture {index} reviewer B"
        )
        progress_a["dataset_sha256"] = hashlib.sha256(
            dataset_a_bytes
        ).hexdigest()
        progress_b["dataset_sha256"] = hashlib.sha256(
            dataset_b_bytes
        ).hexdigest()

        session_id = expected["capture_provenance"]["capture_session_id"]
        screenshot_hash = expected["source_screenshot_sha256"]
        if session_id in session_ids:
            raise ValueError(f"Manifest repeats capture session_id: {session_id}")
        if screenshot_hash in screenshot_hashes:
            raise ValueError("Manifest repeats an identical source screenshot")
        session_ids.add(session_id)
        screenshot_hashes.add(screenshot_hash)

        for key in (
            "sample_count", "reviewed_count", "confirmed_count",
            "ambiguous_count", "not_reviewed_count",
        ):
            reviewer_a_totals[key] += progress_a[key]
            reviewer_b_totals[key] += progress_b[key]
        total_samples += progress_a["sample_count"]

        blockers = []
        for reviewer_name, progress in (
            ("reviewer_a", progress_a),
            ("reviewer_b", progress_b),
        ):
            if not progress["complete"]:
                blockers.append(f"{reviewer_name}_has_unreviewed_samples")
            if not progress["agreement_eligible"]:
                blockers.append(f"{reviewer_name}_has_no_confirmed_samples")

        capture_reports.append({
            "capture_index": index,
            "capture_session_id": session_id,
            "source_detection_sha256": expected["source_detection_sha256"],
            "source_screenshot_sha256": screenshot_hash,
            "source_artifacts_verified": True,
            "reviewer_a": progress_a,
            "reviewer_b": progress_b,
            "paired_review_complete": (
                progress_a["complete"] and progress_b["complete"]
            ),
            "paired_agreement_eligible": (
                progress_a["agreement_eligible"]
                and progress_b["agreement_eligible"]
            ),
            "agreement_blockers": blockers,
        })

    capture_count = len(capture_reports)
    readiness_blockers = [
        {
            "capture_index": item["capture_index"],
            "capture_session_id": item["capture_session_id"],
            "blockers": item["agreement_blockers"],
        }
        for item in capture_reports
        if item["agreement_blockers"]
    ]
    ready = not readiness_blockers

    def totals(counts, reviewer_key):
        reviewed = counts["reviewed_count"]
        slots = counts["sample_count"]
        agreement_eligible = all(
            item[reviewer_key]["agreement_eligible"]
            for item in capture_reports
        )
        return {
            "sample_count": slots,
            "reviewed_count": reviewed,
            "confirmed_count": counts["confirmed_count"],
            "ambiguous_count": counts["ambiguous_count"],
            "not_reviewed_count": counts["not_reviewed_count"],
            "completion_rate": round(reviewed / slots, 6) if slots else None,
            "complete": counts["not_reviewed_count"] == 0,
            "agreement_eligible": agreement_eligible,
        }

    return {
        "schema_version": 1,
        "evaluator": "shooter_review_intake_audit",
        "reviewer_a_id": reviewer_a_id,
        "reviewer_b_id": reviewer_b_id,
        "capture_count": capture_count,
        "sample_count": total_samples,
        "reviewer_a": totals(reviewer_a_totals, "reviewer_a"),
        "reviewer_b": totals(reviewer_b_totals, "reviewer_b"),
        "agreement_audit_ready": ready,
        "readiness_blockers": readiness_blockers,
        "captures": capture_reports,
        "source_provenance": {
            "all_capture_sources_verified": True,
            "distinct_capture_sessions": len(session_ids),
            "distinct_source_screenshots": len(screenshot_hashes),
        },
        "reviewer_independence_verified": False,
        "label_truth_independently_verified": False,
        "agreement_evaluated": False,
        "gameplay_verified": False,
        "game_taps_enabled": False,
        "interpretation": (
            "Readiness means both reviewer files are complete, source-bound, "
            "and each contains at least one confirmed sample for every capture. "
            "The agreement evaluator rejects a reviewer dataset with zero "
            "confirmed samples. Readiness does not mean reviewers are "
            "independent, labels are correct, reviewers agree, or gameplay is "
            "verified. Run shooter_batch_review_agreement.py only after this "
            "audit reports agreement_audit_ready = true."
        ),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Check source-bound paired shooter-review completion progress"
    )
    parser.add_argument("manifest", help="review_manifest.json")
    parser.add_argument("--reviewer-a-id", required=True)
    parser.add_argument("--reviewer-b-id", required=True)
    parser.add_argument(
        "--output", default="data/shooter_review_intake_audit.json"
    )
    parser.add_argument(
        "--require-ready",
        action="store_true",
        help=(
            "Exit with status 1 after saving the report when any reviewer "
            "has an unfinished slot or no confirmed sample in any capture"
        ),
    )
    args = parser.parse_args()

    manifest_path = Path(args.manifest).expanduser().resolve()
    try:
        manifest = strict_json_loads(manifest_path.read_bytes())
        report = audit_review_intake(
            manifest,
            manifest_path.parent,
            args.reviewer_a_id,
            args.reviewer_b_id,
        )
        output = Path(args.output).expanduser().resolve()
        protected_inputs = {manifest_path}
        for entry in manifest.get("captures", []):
            if not isinstance(entry, dict):
                continue
            for field in (
                "reviewer_a_dataset", "reviewer_b_dataset",
                "detection", "screenshot",
            ):
                value = entry.get(field)
                if isinstance(value, str) and value.strip():
                    candidate = Path(value).expanduser()
                    if not candidate.is_absolute():
                        candidate = manifest_path.parent / candidate
                    protected_inputs.add(candidate.resolve())
        temporary = output.with_suffix(output.suffix + ".tmp")
        if output in protected_inputs or temporary in protected_inputs:
            raise ValueError(
                "Output and temporary output paths must not overwrite input artifacts"
            )
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_text(
            json.dumps(report, indent=2) + "\n", encoding="utf-8"
        )
        temporary.replace(output)
    except (OSError, TypeError, UnicodeDecodeError, ValueError) as exc:
        parser.error(str(exc))

    print("SLIME AI — PAIRED REVIEW INTAKE")
    print("Verified captures:", report["capture_count"])
    print(
        "Reviewer A completion:",
        report["reviewer_a"]["reviewed_count"],
        "/",
        report["reviewer_a"]["sample_count"],
    )
    print(
        "Reviewer B completion:",
        report["reviewer_b"]["reviewed_count"],
        "/",
        report["reviewer_b"]["sample_count"],
    )
    print("Ready for agreement audit:", report["agreement_audit_ready"])
    if report["readiness_blockers"]:
        print("Readiness blockers:")
        blocker_labels = {
            "reviewer_a_has_unreviewed_samples": (
                "Reviewer A has unreviewed slots."
            ),
            "reviewer_b_has_unreviewed_samples": (
                "Reviewer B has unreviewed slots."
            ),
            "reviewer_a_has_no_confirmed_samples": (
                "Reviewer A needs at least one confirmed sample."
            ),
            "reviewer_b_has_no_confirmed_samples": (
                "Reviewer B needs at least one confirmed sample."
            ),
        }
        for item in report["readiness_blockers"]:
            print(
                f"  Capture {item['capture_index'] + 1} "
                f"({item['capture_session_id']}):"
            )
            for blocker in item["blockers"]:
                print(
                    "    -",
                    blocker_labels.get(
                        blocker, blocker.replace("_", " ")
                    ),
                )
    else:
        print("Readiness blockers: none")
    print("Reviewer independence verified: False")
    print("Label truth independently verified: False")
    print("Gameplay verified: False")
    print("Game taps enabled: False")
    print("Report:", output)

    if args.require_ready and not report["agreement_audit_ready"]:
        parser.exit(
            1,
            "ERROR: Readiness gate failed; the intake report was saved, "
            "but a capture is incomplete or a reviewer has no confirmed sample.\n",
        )


if __name__ == "__main__":
    main()
