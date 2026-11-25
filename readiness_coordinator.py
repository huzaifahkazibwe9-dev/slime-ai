"""Slime AI integration and readiness coordinator.

Read-only with respect to gameplay, MacroDroid and learning data.
Writes only its diagnostic JSON report.
"""
import argparse
import json
import sqlite3
from pathlib import Path

from level_loader import load_level
from planner import plan_next_move
from resource_manager import ResourceManager

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
REPORT = DATA / "readiness_report.json"

def read_json(name, default=None):
    path = DATA / name
    if not path.exists():
        return default
    try:
        value = json.loads(path.read_text())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return default
    return value if isinstance(value, dict) else default

def learning_summary():
    db = DATA / "learning.db"
    if not db.exists():
        return {"available": False, "gameplay_records": 0}
    try:
        connection = sqlite3.connect(
            f"file:{db}?mode=ro", uri=True
        )
        columns = {
            row[1] for row in
            connection.execute("PRAGMA table_info(observations)")
        }
        if "source" not in columns:
            connection.close()
            return {
                "available": True,
                "gameplay_records": 0,
                "note": "Source column unavailable"
            }
        count = connection.execute(
            "SELECT COUNT(*) FROM observations "
            "WHERE source='gameplay'"
        ).fetchone()[0]
        connection.close()
        return {"available": True, "gameplay_records": count}
    except sqlite3.Error as error:
        return {"available": False, "error": str(error)}

def assess(state, audit, calibration, identity, firing,
           capture_preflight_verified=False):
    # Evidence artifacts are external JSON inputs; malformed top-level shapes
    # should produce unavailable checks, not crash readiness reporting.
    audit = audit if isinstance(audit, dict) else {}
    calibration = calibration if isinstance(calibration, dict) else {}
    identity = identity if isinstance(identity, dict) else {}
    firing = firing if isinstance(firing, dict) else {}
    errors = state.validate()
    mapping_verified = bool(state.colour_mappings_verified)
    accessible = len(state.accessible_shooters())

    checks = {
        "board_dimensions_35x35": (
            state.width == 35 and state.height == 35
        ),
        "all_1225_starting_tiles_preserved": (
            state.remaining_pixels == 1225
        ),
        "game_state_valid": not errors,
        "initial_occupancy_user_confirmed": (
            audit.get("initial_occupancy_user_confirmed") is True
        ),
        "colour_classification_verified": (
            audit.get("colour_classification_verified") is True
        ),
        "source_pixel_capture_preflight_verified": (
            capture_preflight_verified is True
        ),
        "shooter_capture_provenance_verified": (
            capture_preflight_verified is True
            and audit.get("shooter_capture_provenance_verified") is True
        ),
        "colour_mappings_gameplay_verified": mapping_verified,
        "at_least_one_accessible_shooter": accessible > 0,
        "conveyor_calibration_present": bool(
            calibration
            and isinstance(calibration.get("shooters"), list)
            and calibration["shooters"]
        ),
        "conveyor_timing_calibrated": bool(
            calibration
            and isinstance(calibration.get("shooters"), list)
            and calibration["shooters"]
            and calibration.get("timing_calibrated_to_game") is True
            and calibration.get("verified_by_user") is True
        ),
        "physical_shooter_identity_verified": bool(
            identity
            and identity.get("identity_verified") is True
            and identity.get("verified_by_user") is True
            and identity.get("timestamps_known") is True
            and identity.get("timestamp_identified") is True
            and identity.get("errors") == []
            and identity.get("blockers") == []
        ),
        # No independent firing-verification pipeline exists yet. A JSON
        # boolean is only a claim and must never promote this readiness check.
        "actual_firing_verified": False,
        "actual_firing_verification_available": False,
        "actual_firing_claim_ignored": (
            firing.get("actual_firing_verified") is True
        ),
        # These are implementation/authorization prerequisites, not evidence
        # flags that a JSON report may assert on behalf of the user.
        "live_execution_path_implemented": False,
        "live_gameplay_validation_complete": False,
        "explicit_live_execution_opt_in": False,
    }

    return {
        "checks": checks,
        "validation_errors": errors,
        "accessible_shooters": accessible,
        "remaining_pixels": state.remaining_pixels,
        "diagnostic_ready": (
            checks["board_dimensions_35x35"]
            and checks["all_1225_starting_tiles_preserved"]
            and checks["game_state_valid"]
        ),
        # This project deliberately has no live tap pathway.
        "game_taps_enabled": False,
        "autonomous_play_ready": False,
        "live_execution_blockers": [
            name for name in (
                "live_execution_path_implemented",
                "live_gameplay_validation_complete",
                "explicit_live_execution_opt_in",
            )
            if not checks[name]
        ],
    }

def main(observation_path=None, shooter_path=None):
    print("=" * 55)
    print("SLIME AI — READINESS COORDINATOR")
    print("=" * 55)

    from orchestration import (
        _canonical_json_sha256,
        _read_capture_bundle,
        _read_planning_evidence_bundle,
    )
    pinned_capture = None
    if observation_path is not None:
        board_path = Path(observation_path)
        shooter_file = Path(shooter_path or "data/shooter_detection.json")
        pixel_audit_path = board_path.parent / "source_pixel_audit_latest.json"
        if (
            board_path.is_file()
            and shooter_file.is_file()
            and pixel_audit_path.is_file()
        ):
            pinned_capture = _read_capture_bundle(board_path, shooter_file)
            from capture_preflight import validate_capture_pair
            capture = validate_capture_pair(
                board_path,
                shooter_file,
                board_data=pinned_capture["board_data"],
                shooter_data=pinned_capture["shooter_data"],
                pixel_audit_data=pinned_capture["pixel_audit_data"],
            )
            if capture.get("valid") is not True:
                raise ValueError(capture.get("reason", "Capture preflight failed."))
            state, audit = load_level(
                level=39,
                observation_path=board_path,
                shooter_path=shooter_file,
                observation_data=capture["board_data"],
                shooter_data=capture["shooter_data"],
            )
            board_observation = capture["board_data"]
        else:
            # Preserve the diagnostic report when a capture artifact is
            # incomplete; the planner remains blocked without pinned bytes.
            state, audit = load_level(
                level=39,
                observation_path=board_path,
                shooter_path=shooter_file,
            )
            board_observation = {}
    else:
        state, audit = load_level(level=39)
        board_observation = read_json("board_observation_latest.json", {})

    evidence_bundle = _read_planning_evidence_bundle(DATA)
    current_source_file_sha256 = dict(evidence_bundle["file_sha256"])
    if pinned_capture is not None:
        current_source_file_sha256["board_observation_json"] = (
            pinned_capture["board_bytes_sha256"]
        )
    calibration = evidence_bundle["conveyor_calibration"] or {}
    identity = evidence_bundle["identity"] or {}
    firing = read_json("firing_observations.json", {})
    planning = evidence_bundle["planning"]
    identity_audit = evidence_bundle["identity"]
    candidate_report = evidence_bundle["candidates"]
    snapshot_report = evidence_bundle["snapshot"]
    conveyor_observation = evidence_bundle["conveyor_observation"]
    learning = learning_summary()

    result = assess(
        state, audit, calibration, identity, firing,
        capture_preflight_verified=pinned_capture is not None,
    )
    manager = ResourceManager()

    # Apply the same cross-artifact capture gate as orchestration.
    from snapshot_sync import synchronise_bundle
    from orchestration import evidence_status

    bundle_sync = synchronise_bundle(
        board_observation,
        conveyor_observation,
        identity_audit,
        candidate_report,
        planning,
    )
    synchronized_snapshot = (
        dict(snapshot_report) if isinstance(snapshot_report, dict) else {}
    )
    synchronized_snapshot["synchronised"] = (
        synchronized_snapshot.get("synchronised") is True
        and bundle_sync["synchronised"]
    )
    synchronized_snapshot["planning_allowed_by_sync"] = (
        synchronized_snapshot.get("planning_allowed_by_sync") is True
        and bundle_sync["planning_allowed_by_sync"]
    )
    synchronized_snapshot["bundle_synchronisation"] = bundle_sync
    current_calibration_sha256 = _canonical_json_sha256(
        evidence_bundle["vision_calibration"]
    )
    gate = evidence_status(
        planning, identity_audit, synchronized_snapshot, candidate_report,
        shooter_capture_verified=(
            audit.get("shooter_capture_provenance_verified") is True
        ),
        planning_input_file_sha256=current_source_file_sha256,
        board_calibration_sha256=(
            board_observation.get("calibration_sha256")
            if isinstance(board_observation, dict) else None
        ),
        current_calibration_sha256=current_calibration_sha256,
    )

    shooter_capture_verified = (
        pinned_capture is not None
        and audit.get("shooter_capture_provenance_verified") is True
    )
    manager.set_mode("ANALYSE")
    candidate = None
    if gate["evidence_gate_passed"] and shooter_capture_verified:
        candidate = plan_next_move(
            state,
            planning_report=planning,
            identity_audit=identity_audit,
            candidate_report=candidate_report,
            snapshot_report=synchronized_snapshot,
            current_source_file_sha256=current_source_file_sha256,
            current_calibration_sha256=current_calibration_sha256,
            current_identity_audit=identity_audit,
            current_board_observation=board_observation if pinned_capture is not None else None,
        )
    manager.stop()
    result["planning_evidence_gate"] = gate
    result["shooter_capture_provenance_verified"] = shooter_capture_verified
    result["evidence_bundle_synchronisation"] = bundle_sync

    result["level"] = state.level
    result["shooters"] = {
        shooter_id: {
            "colour": shooter.color,
            "ammo": shooter.ammo,
            "accessible": shooter.accessible,
            "bonded_ids": shooter.bonded_ids,
        }
        for shooter_id, shooter in state.shooters.items()
    }
    result["planner_candidate"] = (
        list(candidate) if candidate else None
    )
    result["learning"] = learning
    result["resource_manager"] = manager.status()
    result["vision_audit"] = audit
    result["calibration_user_confirmed"] = bool(
        calibration.get("verified_by_user", False)
    )
    result["actual_game_actions_performed"] = False

    DATA.mkdir(exist_ok=True)
    REPORT.write_text(json.dumps(result, indent=2))

    print("\nREADINESS CHECKS")
    for name, passed in result["checks"].items():
        print(f"[{'PASS' if passed else 'PENDING'}] {name}")

    print("\nDIAGNOSTIC READY:", result["diagnostic_ready"])
    print("Accessible shooters:", result["accessible_shooters"])
    print("Planner candidate:", result["planner_candidate"])
    print("Gameplay learning records:",
          learning.get("gameplay_records", 0))
    print("Game taps enabled:", result["game_taps_enabled"])
    print("Autonomous play ready:",
          result["autonomous_play_ready"])
    print("\nReport:", REPORT)
    print("No game actions were performed.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Assess Slime AI readiness from current evidence"
    )
    parser.add_argument(
        "--observation",
        help="Screenshot-ingestor JSON for the current board",
    )
    parser.add_argument(
        "--shooters",
        default="data/shooter_detection.json",
        help="Shooter detection JSON used with --observation",
    )
    args = parser.parse_args()
    main(
        observation_path=args.observation,
        shooter_path=args.shooters if args.observation else None,
    )
