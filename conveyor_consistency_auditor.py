import json
from pathlib import Path

DATA = Path("data")
TIMELINE_FILE = DATA / "conveyor_timeline.json"
OBSERVATIONS_FILE = DATA / "conveyor_visual_observations.json"
OUTPUT_FILE = DATA / "conveyor_consistency_report.json"

EXPECTED_ORDER = ["bottom", "right", "top", "left"]

TRACKS = {
    "white": {
        "shooter": "top_1",
        "keys": [
            "bottom_1", "right_2", "top_2", "left_1"
        ],
    },
    "blue_cyan": {
        "shooter": "top_2",
        "keys": [
            "bottom_2", "right_1", "top_1", "left_2"
        ],
    },
}


def load_json(path):
    if not path.exists():
        raise FileNotFoundError(f"Required file missing: {path}")
    return json.loads(path.read_text())


def audit(timeline, original_data):
    """Compare a candidate timeline with the observations it claims to preserve.

    Identity and gameplay flags are forced off. A consistent report is still
    only candidate data: ammunition order does not prove shooter identity.
    """
    if not isinstance(timeline, dict) or not isinstance(original_data, dict):
        raise ValueError("Timeline and observations must be JSON objects")

    observations = original_data.get("observations")
    if not isinstance(observations, list):
        raise ValueError("Observations are missing an observations list")

    errors = []
    warnings = []
    results = {}
    original = {}

    for index, item in enumerate(observations):
        if not isinstance(item, dict):
            errors.append(f"Original observation {index} must be an object.")
            continue

        position_id = item.get("position_id")
        if not isinstance(position_id, str) or not position_id.strip():
            errors.append(
                f"Original observation {index} has an invalid position_id."
            )
            continue

        if position_id in original:
            errors.append(
                f"Duplicate original observation position_id: {position_id}."
            )
            continue

        original[position_id] = item

    if timeline.get("sequence") != EXPECTED_ORDER:
        errors.append("Timeline stage order does not match expected order.")

    snapshots = timeline.get("snapshots", [])
    if not isinstance(snapshots, list):
        errors.append("Timeline snapshots must be a list.")
        snapshots = []

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
                    f"Timeline snapshot at position {index + 1} must be an object."
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

            if not isinstance(ammo, int) or isinstance(ammo, bool) or ammo < 0:
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
            "candidate_shooter": config["shooter"],
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
            "identity_status": "candidate_only_unverified",
        }

    return {
        "report_type": "conveyor_consistency_audit",
        "sequence": EXPECTED_ORDER,
        "sequence_confirmed_by_user": timeline.get(
            "sequence_confirmed_by_user", False
        ),
        "timestamps_known": timeline.get("timestamps_known", False),
        "identity_verified": False,
        "gameplay_taps_enabled": False,
        "candidate_tracks": results,
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
            "CONSISTENT_CANDIDATE_DATA"
            if not errors
            else "INCONSISTENCIES_FOUND"
        ),
        "limitations": [
            "Screenshot timestamps are unknown.",
            "Shooter identity has not been independently verified.",
            "Ammunition consistency alone cannot prove physical identity.",
            "No live gameplay or firing behaviour was tested.",
        ],
    }


def main():
    timeline = load_json(TIMELINE_FILE)
    original_data = load_json(OBSERVATIONS_FILE)
    report = audit(timeline, original_data)

    OUTPUT_FILE.write_text(json.dumps(report, indent=2))

    print("=" * 52)
    print("SLIME AI — CONVEYOR CONSISTENCY AUDITOR")
    print("=" * 52)

    for name, result in report["candidate_tracks"].items():
        print(f"\n{name.upper()} — {result['candidate_shooter']}")
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
    print("Report:", OUTPUT_FILE)
    return report


if __name__ == "__main__":
    main()
