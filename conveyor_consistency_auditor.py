import hashlib
import json
from pathlib import Path

DATA = Path("data")
TIMELINE_FILE = DATA / "conveyor_timeline.json"
OBSERVATIONS_FILE = DATA / "conveyor_visual_observations.json"
OUTPUT_FILE = DATA / "conveyor_consistency_report.json"

EXPECTED_ORDER = ["bottom", "right", "top", "left"]

TRACKS = {
    "white": {
        "keys": [
            "bottom_1", "right_2", "top_2", "left_1"
        ],
    },
    "blue_cyan": {
        "keys": [
            "bottom_2", "right_1", "top_1", "left_2"
        ],
    },
}


def read_json_snapshot(path):
    raw = Path(path).read_bytes()
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Evidence file is not valid UTF-8 JSON: {path}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"Evidence file must contain a JSON object: {path}")
    return value, hashlib.sha256(raw).hexdigest()


def build_consistency_report(timeline, original_data, source_file_sha256=None):
    if not isinstance(timeline, dict) or not isinstance(original_data, dict):
        raise ValueError("Timeline and observation inputs must be JSON objects")
    observation_list = original_data.get("observations")
    if not isinstance(observation_list, list):
        raise ValueError("Original conveyor observations must be a list")
    original = {}
    for index, item in enumerate(observation_list):
        if not isinstance(item, dict):
            raise ValueError(f"Original observation {index} must be an object")
        position_id = item.get("position_id")
        if not isinstance(position_id, str) or not position_id:
            raise ValueError(f"Original observation {index} has an invalid position ID")
        if position_id in original:
            raise ValueError(f"Duplicate original conveyor position: {position_id}")
        original[position_id] = item


    errors = []
    warnings = []
    results = {}

    if timeline.get("sequence") != EXPECTED_ORDER:
        errors.append("Timeline stage order does not match expected order.")

    snapshots = timeline.get("snapshots")
    if not isinstance(snapshots, list):
        raise ValueError("Timeline snapshots must be a list")

    if len(snapshots) != 4:
        errors.append(
            f"Expected 4 timeline snapshots; found {len(snapshots)}."
        )

    for track_name, config in TRACKS.items():
        key = (
            "white_candidate"
            if track_name == "white"
            else "blue_cyan_candidate"
        )

        ammo_values = []
        positions = []
        preservation_checks = []

        for index, step in enumerate(snapshots):
            if index >= len(EXPECTED_ORDER):
                break

            expected_side = EXPECTED_ORDER[index]
            if not isinstance(step, dict):
                errors.append(
                    f"{track_name}: timeline step {index + 1} is not an object."
                )
                continue

            if step.get("side") != expected_side:
                errors.append(
                    f"{track_name}: unexpected stage at position {index + 1}."
                )

            item = step.get(key)

            if not isinstance(item, dict):
                errors.append(
                    f"{track_name}: missing observation at {expected_side}."
                )
                continue

            position_id = item.get("position_id")
            positions.append(position_id)

            expected_position = config["keys"][index]
            if position_id != expected_position:
                errors.append(
                    f"{track_name}: expected {expected_position}, "
                    f"but found {position_id} at {expected_side}."
                )

            if position_id not in original:
                errors.append(
                    f"{track_name}: {position_id} missing from original data."
                )
                preservation_checks.append(False)
                continue

            preserved = item == original[position_id]
            preservation_checks.append(preserved)

            if not preserved:
                errors.append(
                    f"{track_name}: {position_id} differs from original data."
                )

            ammo = item.get("ammo")

            if type(ammo) is not int or ammo < 0:
                errors.append(
                    f"{track_name}: invalid ammunition at {position_id}."
                )
                continue

            ammo_values.append(ammo)

        deltas = []
        increases = []
        unchanged = []

        for i in range(1, len(ammo_values)):
            previous = ammo_values[i - 1]
            current = ammo_values[i]
            change = previous - current

            deltas.append({
                "from_stage": EXPECTED_ORDER[i - 1],
                "to_stage": EXPECTED_ORDER[i],
                "ammo_before": previous,
                "ammo_after": current,
                "ammo_spent": change,
            })

            if current > previous:
                increases.append({
                    "stage": EXPECTED_ORDER[i],
                    "previous": previous,
                    "current": current,
                })

            elif current == previous:
                unchanged.append(EXPECTED_ORDER[i])

        if increases:
            errors.append(
                f"{track_name}: ammunition increased between observations."
            )

        if unchanged:
            warnings.append(
                f"{track_name}: unchanged ammunition at "
                + ", ".join(unchanged)
                + ". This is not automatically an error."
            )

        if ammo_values and ammo_values[-1] == 0:
            depletion = "zero_ammunition_observed"
        else:
            depletion = "zero_ammunition_not_observed"

        results[track_name] = {
            "positions": positions,
            "ammunition": ammo_values,
            "ammunition_changes": deltas,
            "non_increasing": (
                len(ammo_values) > 0
                and all(
                    b <= a
                    for a, b in zip(ammo_values, ammo_values[1:])
                )
            ),
            "unchanged_stages": unchanged,
            "increases": increases,
            "depletion_status": depletion,
            "original_observations_preserved": (
                len(preservation_checks) == len(positions)
                and all(preservation_checks)
            ),
            "identity_status": "UNRESOLVED_POSITION_SERIES_ONLY",
        }

    report = {
        "report_type": "conveyor_consistency_audit",
        "sequence": EXPECTED_ORDER,
        "sequence_confirmed_by_user": timeline.get(
            "sequence_confirmed_by_user", False
        ),
        "timestamps_known": timeline.get("timestamps_known") is True,
        "identity_verified": False,
        "gameplay_taps_enabled": False,
        "position_series": results,
        "source_file_sha256": source_file_sha256 or {},
        "source_file_sha256": source_file_sha256 or {},
        "checks": {
            "timeline_has_four_stages": len(snapshots) == 4,
            "stage_order_valid": (
                timeline.get("sequence") == EXPECTED_ORDER
            ),
            "original_observations_preserved": (
                not any("differs from original" in e for e in errors)
            ),
            "no_ammunition_increases": not any(
                "ammunition increased" in e for e in errors
            ),
        },
        "errors": errors,
        "warnings": warnings,
        "overall_status": (
            "CONSISTENT_POSITION_DATA"
            if not errors
            else "INCONSISTENCIES_FOUND"
        ),
        "limitations": [
            "Timestamps are not independently verified by this consistency check.",
            "This report contains position-based ammunition trends only; no physical shooter identity is assigned.",
            "Ammunition consistency alone cannot prove physical identity.",
            "No live gameplay or firing behaviour was tested.",
        ],
    }

    return report


def main(timeline_path=TIMELINE_FILE, observations_path=OBSERVATIONS_FILE,
         output_path=OUTPUT_FILE):
    try:
        timeline, timeline_digest = read_json_snapshot(timeline_path)
        original_data, observations_digest = read_json_snapshot(observations_path)
        report = build_consistency_report(
            timeline,
            original_data,
            {
                "conveyor_timeline_json": timeline_digest,
                "conveyor_visual_observations_json": observations_digest,
            },
        )
    except (OSError, ValueError) as exc:
        report = {
            "report_type": "conveyor_consistency_audit",
            "sequence": EXPECTED_ORDER,
            "sequence_confirmed_by_user": False,
            "timestamps_known": False,
            "identity_verified": False,
            "gameplay_taps_enabled": False,
            "game_taps_enabled": False,
            "position_series": {},
            "source_file_sha256": {},
            "checks": {},
            "errors": [f"{type(exc).__name__}: {exc}"],
            "warnings": [],
            "overall_status": "EVIDENCE_UNAVAILABLE",
            "limitations": [
                "No physical shooter identity is assigned.",
                "No live gameplay or firing behaviour was tested.",
            ],
        }

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(output_path.suffix + ".tmp")
    temporary.write_text(json.dumps(report, indent=2), encoding="utf-8")
    temporary.replace(output_path)

    print("=" * 52)
    print("SLIME AI — CONVEYOR CONSISTENCY AUDITOR")
    print("=" * 52)

    for name, result in report["position_series"].items():
        print(f"\n{name.upper()} — POSITION SERIES ONLY")
        print("Positions:", result["positions"])
        print("Ammunition:", result["ammunition"])
        print("Non-increasing:", result["non_increasing"])
        print("Original observations preserved:",
              result["original_observations_preserved"])
        print("Depletion:", result["depletion_status"])

        for delta in result["ammunition_changes"]:
            print(
                f"  {delta['from_stage']} -> {delta['to_stage']}: "
                f"spent {delta['ammo_spent']}"
            )

    print("\nCHECKS")
    for name, passed in report["checks"].items():
        print(f"[{'PASS' if passed else 'FAIL'}] {name}")

    for warning in report["warnings"]:
        print("[WARNING]", warning)

    for error in report["errors"]:
        print("[ERROR]", error)

    print("\nOverall:", report["overall_status"])
    print("Identity verified: False")
    print("Gameplay taps enabled: False")
    print("Report:", output_path)
    return report


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(
        description="Audit position-based ammunition consistency without identity inference"
    )
    parser.add_argument("--timeline", default=str(TIMELINE_FILE))
    parser.add_argument("--observations", default=str(OBSERVATIONS_FILE))
    parser.add_argument("--output", default=str(OUTPUT_FILE))
    args = parser.parse_args()
    main(Path(args.timeline), Path(args.observations), Path(args.output))
