import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

INPUT_FILE = Path("data/reachability_confidence_latest.json")
OUTPUT_FILE = Path("data/planning_gate_latest.json")


def _parse_aware_timestamp(value):
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def _valid_capture_session_id(value):
    return (
        isinstance(value, str)
        and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", value) is not None
    )


def _valid_snapshot_id(value):
    return (
        isinstance(value, str)
        and re.fullmatch(r"sha256:[0-9a-f]{64}", value) is not None
    )


def _capture_provenance(report):
    snapshot_id = report.get("board_snapshot_id")
    session_id = report.get("capture_session_id")
    captured_at = _parse_aware_timestamp(report.get("captured_at"))
    valid = (
        _valid_snapshot_id(snapshot_id)
        and _valid_capture_session_id(session_id)
        and report.get("timestamp_identified") is True
        and captured_at is not None
    )
    return {"valid": valid, "captured_at": captured_at}

def _candidate_capture_provenance(candidate_report, board_provenance):
    """Independently validate every candidate track against the planning capture."""
    if not isinstance(candidate_report, dict) or not board_provenance.get("valid"):
        return False
    tracks = candidate_report.get("tracks")
    expected_positions = {
        "white": {"bottom_1", "right_2", "top_2", "left_1"},
        "blue_cyan": {"bottom_2", "right_1", "top_1", "left_2"},
    }
    if not isinstance(tracks, dict) or set(tracks) != set(expected_positions):
        return False

    board_snapshot_id = candidate_report.get("board_snapshot_id")
    session_id = candidate_report.get("capture_session_id")
    captured_at = _parse_aware_timestamp(candidate_report.get("captured_at"))
    board_time = board_provenance.get("captured_at")
    if (
        not _valid_snapshot_id(board_snapshot_id)
        or not _valid_capture_session_id(session_id)
        or captured_at is None
        or board_snapshot_id != board_provenance.get("board_snapshot_id")
        or session_id != board_provenance.get("capture_session_id")
        or candidate_report.get("timestamp_identified") is not True
        or board_time is None
        or abs((captured_at - board_time).total_seconds()) > 120
    ):
        return False

    for track_name, track in tracks.items():
        if not isinstance(track, dict):
            return False
        if (
            track.get("board_snapshot_id") != board_snapshot_id
            or track.get("capture_session_id") != session_id
            or track.get("timestamp_identified") is not True
        ):
            return False
        track_time = _parse_aware_timestamp(track.get("captured_at"))
        if (
            track_time is None
            or abs((track_time - board_time).total_seconds()) > 120
            or abs((track_time - captured_at).total_seconds()) > 120
        ):
            return False
        observations = track.get("observations")
        if not isinstance(observations, list) or len(observations) != 4:
            return False
        observed_positions = []
        for observation in observations:
            if not isinstance(observation, dict):
                return False
            observed_positions.append(observation.get("position_id"))
            observed_time = _parse_aware_timestamp(observation.get("captured_at"))
            if (
                observation.get("board_snapshot_id") != board_snapshot_id
                or observation.get("capture_session_id") != session_id
                or observation.get("timestamp_identified") is not True
                or observed_time is None
                or abs((observed_time - board_time).total_seconds()) > 120
                or abs((observed_time - captured_at).total_seconds()) > 120
                or abs((observed_time - track_time).total_seconds()) > 120
            ):
                return False
        if (
            len(set(observed_positions)) != 4
            or set(observed_positions) != expected_positions[track_name]
        ):
            return False
    return True


def evaluate_planning(report, candidate_report=None, conveyor_calibration=None,
                      input_file_sha256=None):
    confidence_audit = report.get("confidence_audit", {})
    board_synced = report.get("same_board_state_confirmed") is True
    freshness = report.get("capture_freshness", {})
    capture_freshness_verified = (
        isinstance(freshness, dict) and freshness.get("fresh") is True
    )
    identity_verified = report.get("conveyor_identity_verified") is True
    provenance = _capture_provenance(report)
    provenance["board_snapshot_id"] = report.get("board_snapshot_id")
    provenance["capture_session_id"] = report.get("capture_session_id")
    candidate_provenance_verified = _candidate_capture_provenance(
        candidate_report, provenance
    )
    mappings_verified = report.get("gameplay_verified") is True
    conveyor_timing_calibrated = (
        isinstance(conveyor_calibration, dict)
        and conveyor_calibration.get("timing_calibrated_to_game") is True
        and conveyor_calibration.get("verified_by_user") is True
    )
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
            ammo_observed_at = _parse_aware_timestamp(
                ammo_evidence.get("observed_at")
                if isinstance(ammo_evidence, dict) else None
            )
            ammo_timestamp_aligned = (
                provenance["captured_at"] is not None
                and ammo_observed_at is not None
                and abs((ammo_observed_at - provenance["captured_at"]).total_seconds()) <= 120
            )
            ammo_evidence_valid = (
                isinstance(ammo_evidence, dict)
                and ammo_evidence.get("verified") is True
                and ammo_evidence.get("position_id") == position.get("position_id")
                and type(ammo_evidence.get("ammo")) is int
                and ammo_evidence.get("ammo") == ammo
                and _valid_capture_session_id(ammo_evidence.get("capture_session_id"))
                and ammo_evidence.get("capture_session_id") == report.get("capture_session_id")
                and _valid_snapshot_id(ammo_evidence.get("board_snapshot_id"))
                and ammo_evidence.get("board_snapshot_id") == report.get("board_snapshot_id")
                and ammo_timestamp_aligned
                and isinstance(ammo_evidence.get("checks"), dict)
                and set(ammo_evidence.get("checks", {})) == {
                    "ammo_is_non_negative_integer",
                    "position_identity_matches",
                    "capture_session_present",
                    "board_snapshot_present",
                    "observation_timestamp_present",
                    "explicit_user_confirmation",
                }
                and all(value is True for value in ammo_evidence.get("checks", {}).values())
            )
            if not ammo_evidence_valid:
                blockers.append("AMMUNITION_OBSERVATION_UNVERIFIED")
            if not provenance["valid"]:
                blockers.append("BOARD_CAPTURE_PROVENANCE_INCOMPLETE")
            if not candidate_provenance_verified:
                blockers.append("CANDIDATE_CAPTURE_PROVENANCE_UNVERIFIED")
            if not board_synced:
                blockers.append("BOARD_STATE_NOT_SYNCHRONISED")
            if not capture_freshness_verified:
                blockers.append("CAPTURE_TIMESTAMPS_NOT_FRESH_AND_ALIGNED")
            if not identity_verified or position.get("identity_verified") is not True:
                blockers.append("SHOOTER_IDENTITY_UNVERIFIED")
            if not mappings_verified:
                blockers.append("GAMEPLAY_COLOUR_MAPPING_UNVERIFIED")
            if not conveyor_timing_calibrated:
                blockers.append("CONVEYOR_TIMING_NOT_USER_CALIBRATED")
            if not confidence_snapshot_verified:
                blockers.append("CONFIDENCE_BOARD_SNAPSHOT_UNVERIFIED")
            if scenario.get("confidence_eligible") is not True:
                blockers.append("LANE_CONFIDENCE_UNCONFIRMED")
            if position.get("planning_eligible") is not True:
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
                "evidence_trace": {
                    "board_capture": {
                        "board_snapshot_id": report.get("board_snapshot_id"),
                        "capture_session_id": report.get("capture_session_id"),
                        "captured_at": report.get("captured_at"),
                        "timestamp_identified": report.get("timestamp_identified") is True,
                    },
                    "shooter_observation": {
                        "position_id": (
                            ammo_evidence.get("position_id")
                            if isinstance(ammo_evidence, dict) else None
                        ),
                        "ammo": (
                            ammo_evidence.get("ammo")
                            if isinstance(ammo_evidence, dict) else None
                        ),
                        "board_snapshot_id": (
                            ammo_evidence.get("board_snapshot_id")
                            if isinstance(ammo_evidence, dict) else None
                        ),
                        "capture_session_id": (
                            ammo_evidence.get("capture_session_id")
                            if isinstance(ammo_evidence, dict) else None
                        ),
                        "observed_at": (
                            ammo_evidence.get("observed_at")
                            if isinstance(ammo_evidence, dict) else None
                        ),
                        "verified": ammo_evidence_valid,
                    },
                    "candidate_capture_provenance_verified": (
                        candidate_provenance_verified
                    ),
                },
                "confidence_eligible": scenario.get("confidence_eligible") is True,
                "planning_eligible": eligible,
                "blockers": blockers,
            })

    return {
        "level": report.get("level"),
        "board_dimensions": report.get("board_dimensions"),
        "board_snapshot_id": report.get("board_snapshot_id"),
        "capture_session_id": report.get("capture_session_id"),
        "captured_at": report.get("captured_at"),
        "timestamp_identified": report.get("timestamp_identified") is True,
        "capture_provenance_verified": provenance["valid"],
        "candidate_capture_provenance_verified": candidate_provenance_verified,
        "capture_freshness_verified": capture_freshness_verified,
        "confidence_snapshot_verified": confidence_snapshot_verified,
        "conveyor_timing_calibrated": conveyor_timing_calibrated,
        "input_file_sha256": (
            dict(input_file_sha256) if isinstance(input_file_sha256, dict) else None
        ),
        "counts": counts,
        "results": results,
        "decision": (
            "ELIGIBLE_CANDIDATES_FOUND"
            if counts["eligible_scenarios"] > 0
            else "NO_VERIFIED_PLANNING_CANDIDATES"
        ),
        # A verified recommendation is not proof of live gameplay or execution.
        "planning_evidence_verified": counts["eligible_scenarios"] > 0,
        "gameplay_verified": False,
        "game_taps_enabled": False,
        "actions_performed": False,
    }


def _read_json_snapshot(path):
    """Parse a JSON object and fingerprint the exact bytes that were parsed."""
    raw = Path(path).read_bytes()
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError(f"Evidence artifact must contain a JSON object: {path}")
    return value, hashlib.sha256(raw).hexdigest()


def main():
    report, reachability_digest = _read_json_snapshot(INPUT_FILE)
    candidate_path = Path("data/conveyor_identity_candidates.json")
    if candidate_path.is_file():
        candidate_report, candidate_digest = _read_json_snapshot(candidate_path)
    else:
        candidate_report, candidate_digest = None, None
    calibration_path = Path("data/conveyor_calibration.json")
    if calibration_path.is_file():
        conveyor_calibration, calibration_digest = _read_json_snapshot(calibration_path)
    else:
        conveyor_calibration, calibration_digest = None, None
    input_file_sha256 = {
        "reachability_confidence_json": reachability_digest,
        "candidate_json": candidate_digest,
        "conveyor_calibration_json": calibration_digest,
    }
    upstream_source_file_sha256 = report.get("upstream_source_file_sha256")
    if not isinstance(upstream_source_file_sha256, dict):
        raise ValueError(
            "Reachability confidence report is missing upstream source hashes"
        )
    result = evaluate_planning(
        report,
        candidate_report=candidate_report,
        conveyor_calibration=conveyor_calibration,
        input_file_sha256=input_file_sha256,
    )
    result["upstream_source_file_sha256"] = dict(upstream_source_file_sha256)
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
