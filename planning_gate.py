import json
from pathlib import Path

INPUT_FILE = Path("data/reachability_confidence_latest.json")
OUTPUT_FILE = Path("data/planning_gate_latest.json")


def evaluate_planning(report):
    confidence_audit = report.get("confidence_audit", {})
    board_synced = bool(report.get("same_board_state_confirmed", False))
    freshness = report.get("capture_freshness", {})
    capture_freshness_verified = (
        isinstance(freshness, dict) and freshness.get("fresh") is True
    )
    identity_verified = bool(report.get("conveyor_identity_verified", False))
    mappings_verified = bool(report.get("gameplay_verified", False))
    confidence_audit = report.get("confidence_audit", {})
    confidence_snapshot_verified = (
        isinstance(confidence_audit, dict)
        and confidence_audit.get("snapshot_match_verified") is True
        and confidence_audit.get("source_snapshot_id")
        == report.get("board_snapshot_id")
        and bool(report.get("board_snapshot_id"))
    )

    results = []
    counts = {
        "scenarios_checked": 0,
        "geometrically_reachable": 0,
        "zero_ammunition": 0,
        "eligible_scenarios": 0,
    }

    for position in report.get("results", []):
        ammo = position.get("observed_ammo")
        ammo_available = type(ammo) is int and ammo > 0

        for scenario in position.get("scenarios", []):
            counts["scenarios_checked"] += 1

            exposed = scenario.get("exposed_matching_count", 0)
            geometrically_reachable = (
                type(exposed) is int and exposed > 0
            )

            if geometrically_reachable:
                counts["geometrically_reachable"] += 1

            if not ammo_available:
                counts["zero_ammunition"] += 1

            blockers = []

            if not geometrically_reachable:
                blockers.append("NO_EXPOSED_MATCHING_PIXELS")
            if not ammo_available:
                blockers.append("NO_REMAINING_AMMUNITION")
            ammo_evidence = position.get("ammo_evidence")
            ammo_evidence_valid = (
                isinstance(ammo_evidence, dict)
                and ammo_evidence.get("verified") is True
                and ammo_evidence.get("position_id") == position.get("position_id")
                and ammo_evidence.get("ammo") == ammo
                and isinstance(ammo_evidence.get("capture_session_id"), str)
                and bool(ammo_evidence.get("capture_session_id").strip())
                and isinstance(ammo_evidence.get("board_snapshot_id"), str)
                and bool(ammo_evidence.get("board_snapshot_id").strip())
                and ammo_evidence.get("board_snapshot_id") == report.get("board_snapshot_id")
                and isinstance(ammo_evidence.get("capture_session_id"), str)
                and ammo_evidence.get("capture_session_id") == report.get("capture_session_id")
                and isinstance(ammo_evidence.get("observed_at"), str)
                and bool(ammo_evidence.get("observed_at").strip())
                and isinstance(ammo_evidence.get("checks"), dict)
                and all(value is True for value in ammo_evidence.get("checks", {}).values())
                and len(ammo_evidence.get("checks", {})) >= 6
            )
            if not ammo_evidence_valid:
                blockers.append("AMMUNITION_OBSERVATION_UNVERIFIED")
            if not board_synced:
                blockers.append("BOARD_STATE_NOT_SYNCHRONISED")
            if not capture_freshness_verified:
                blockers.append("CAPTURE_TIMESTAMPS_NOT_FRESH_AND_ALIGNED")
            if not identity_verified or not position.get(
                "identity_verified", False
            ):
                blockers.append("SHOOTER_IDENTITY_UNVERIFIED")
            if not mappings_verified:
                blockers.append("GAMEPLAY_COLOUR_MAPPING_UNVERIFIED")
            if not confidence_snapshot_verified:
                blockers.append("CONFIDENCE_BOARD_SNAPSHOT_UNVERIFIED")
            if not scenario.get("confidence_eligible", False):
                blockers.append("LANE_CONFIDENCE_UNCONFIRMED")
            if not position.get("planning_eligible", False):
                blockers.append("REACHABILITY_AUDIT_NOT_ELIGIBLE")

            eligible = not blockers

            if eligible:
                counts["eligible_scenarios"] += 1

            results.append({
                "position_id": position.get("position_id"),
                "target_colour": scenario.get("target_colour"),
                "reachability_status": scenario.get("status"),
                "exposed_matching_count": exposed,
                "observed_ammo": ammo,
                "geometrically_reachable": geometrically_reachable,
                "ammunition_available": ammo_available,
                "ammunition_evidence_verified": ammo_evidence_valid,
                "confidence_eligible": bool(
                    scenario.get("confidence_eligible", False)
                ),
                "planning_eligible": eligible,
                "blockers": blockers,
            })

    return {
        "level": report.get("level"),
        "board_dimensions": report.get("board_dimensions"),
        "board_snapshot_id": report.get("board_snapshot_id"),
        "capture_session_id": report.get("capture_session_id"),
        "capture_freshness_verified": capture_freshness_verified,
        "confidence_snapshot_verified": confidence_snapshot_verified,
        "counts": counts,
        "results": results,
        "decision": (
            "ELIGIBLE_CANDIDATES_FOUND"
            if counts["eligible_scenarios"] > 0
            else "NO_VERIFIED_PLANNING_CANDIDATES"
        ),
        "gameplay_verified": False,
        "game_taps_enabled": False,
        "actions_performed": False,
    }


def main():
    report = json.loads(INPUT_FILE.read_text())
    result = evaluate_planning(report)
    OUTPUT_FILE.write_text(json.dumps(result, indent=2))

    print("SLIME AI — BUILD 11H PLANNING GATE")
    print("=" * 48)
    print("Scenarios checked:", result["counts"]["scenarios_checked"])
    print("Geometrically reachable:", result["counts"]["geometrically_reachable"])
    print("Zero-ammunition scenarios:", result["counts"]["zero_ammunition"])
    print("Eligible scenarios:", result["counts"]["eligible_scenarios"])
    print("Decision:", result["decision"])

    print("\nSCENARIO SUMMARY")
    for item in result["results"]:
        print(
            item["position_id"],
            "|", item["target_colour"],
            "| exposed:", item["exposed_matching_count"],
            "| ammo:", item["observed_ammo"],
            "| eligible:", item["planning_eligible"],
            "| blockers:", ", ".join(item["blockers"]),
        )

    print("\nGameplay verified:", result["gameplay_verified"])
    print("Game taps enabled:", result["game_taps_enabled"])
    print("Report:", OUTPUT_FILE)


if __name__ == "__main__":
    main()
