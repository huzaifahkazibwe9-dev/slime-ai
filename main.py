from pathlib import Path
from collections import Counter
import argparse
import json
import sys

# Make module paths independent of the current working directory.
PROJECT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_DIR))

import planner
from level_loader import load_level
from learner import Learner
from resource_manager import ResourceManager


# Real Android interaction remains disabled.
GAME_TAPS_ENABLED = False


def section(title):
    print("\n" + "=" * 48)
    print(title)
    print("=" * 48)


def run_diagnostics(observation_path=None, shooter_path=None, level=39):
    section("SLIME AI CENTRAL DIAGNOSTIC")

    print("Project:", PROJECT_DIR)
    print("Game taps:", "ENABLED" if GAME_TAPS_ENABLED else "DISABLED")
    resource_manager = ResourceManager()
    section("LOW-POWER RESOURCE MANAGEMENT")
    print("Operating mode:", resource_manager.mode.value)
    print("Background loop:", resource_manager.status()["background_loop"])
    print("Timer running:", resource_manager.status()["timer_running"])
    print("Game taps enabled:", resource_manager.game_taps_enabled)

    # Pin screenshot, shooter panel and pixel-audit artifacts before loading.
    section("LEVEL LOADING")
    pinned_capture = None
    if observation_path is not None:
        from orchestration import _read_capture_bundle
        from capture_preflight import validate_capture_pair
        board_path = Path(observation_path)
        shooter_file = Path(shooter_path or "data/shooter_detection.json")
        pixel_audit_path = board_path.parent / "source_pixel_audit_latest.json"
        if (
            board_path.is_file()
            and shooter_file.is_file()
            and pixel_audit_path.is_file()
        ):
            pinned_capture = _read_capture_bundle(board_path, shooter_file)
            capture = validate_capture_pair(
                board_path,
                shooter_file,
                board_data=pinned_capture["board_data"],
                shooter_data=pinned_capture["shooter_data"],
                pixel_audit_data=pinned_capture["pixel_audit_data"],
            )
            if capture.get("valid") is not True:
                raise ValueError(capture.get("reason", "Capture preflight failed."))
            state, vision_verified = load_level(
                level=level,
                observation_path=board_path,
                shooter_path=shooter_file,
                observation_data=capture["board_data"],
                shooter_data=capture["shooter_data"],
            )
        else:
            state, vision_verified = load_level(
                level=level,
                observation_path=board_path,
                shooter_path=shooter_file,
            )
    else:
        state, vision_verified = load_level(level=level)

    print("Level:", state.level)
    print("Board dimensions:", state.width, "x", state.height)
    print("Starting observed tiles:", state.remaining_pixels)
    print("Shooters loaded:", len(state.shooters))
    print("Vision evidence:", vision_verified)

    section("GAME STATE VALIDATION")
    errors = state.validate()
    if errors:
        for error in errors:
            print("ERROR:", error)
    else:
        print("Game-state validation: PASSED")

    print("Conveyor free spaces:", state.conveyor_free)
    print("Storage free spaces:", state.storage_free)

    section("BOARD COLOUR DISTRIBUTION")
    counts = Counter(
        pixel for row in state.board for pixel in row if pixel is not None
    )
    for colour, count in sorted(counts.items()):
        print(f"{colour:12} {count}")

    section("SHOOTER STATUS")
    for shooter_id, shooter in state.shooters.items():
        print(
            shooter_id,
            "| Colour:", shooter.color,
            "| Ammo:", shooter.ammo,
            "| Bonds:", shooter.bonded_ids,
            "| Accessible:", shooter.accessible,
            "| Panel position:", shooter.panel_center,
            "| Conveyor position:", shooter.screen_center,
            "| Direction:", shooter.direction,
        )
    print("Accessible shooters:", len(state.accessible_shooters()))

    section("COLOUR MAPPING STATUS")
    mappings = getattr(state, "colour_mappings", {})
    for shooter_id, mapping in mappings.items():
        print(
            shooter_id, "->", mapping["board_colour"],
            "| Status:", mapping["status"]
        )
    print(
        "Mappings gameplay-verified:",
        getattr(state, "colour_mappings_verified", False),
    )

    section("PLANNER DIAGNOSTIC")
    resource_manager.set_mode("ANALYSE")
    from orchestration import (
        _canonical_json_sha256,
        _read_planning_evidence_bundle,
    )
    evidence_bundle = _read_planning_evidence_bundle(
        PROJECT_DIR / "data",
        pinned_shooter_data=(
            pinned_capture["shooter_data"] if pinned_capture is not None else None
        ),
        pinned_shooter_sha256=(
            pinned_capture["shooter_bytes_sha256"] if pinned_capture is not None else None
        ),
    )
    current_source_file_sha256 = dict(evidence_bundle["file_sha256"])
    board_observation = (
        pinned_capture["board_data"] if pinned_capture is not None else None
    )
    if pinned_capture is not None:
        current_source_file_sha256["board_observation_json"] = (
            pinned_capture["board_bytes_sha256"]
        )
    planning_report = evidence_bundle["planning"]
    identity_report = evidence_bundle["identity"]
    candidate_report = evidence_bundle["candidates"]
    snapshot_report = evidence_bundle["snapshot"]
    conveyor_observation = evidence_bundle["conveyor_observation"]
    board_observation = (
        pinned_capture["board_data"] if pinned_capture is not None else None
    )

    print("Planning report present:", planning_report is not None)
    print("Identity report present:", identity_report is not None)
    print("Candidate report present:", candidate_report is not None)
    print("Snapshot report present:", snapshot_report is not None)

    from snapshot_sync import synchronise_bundle
    from orchestration import evidence_status
    bundle_sync = synchronise_bundle(
        board_observation,
        conveyor_observation,
        identity_report,
        candidate_report,
        planning_report,
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
    planner_gate = evidence_status(
        planning_report,
        identity_report,
        synchronized_snapshot,
        candidate_report,
        shooter_capture_verified=(
            vision_verified.get("shooter_capture_provenance_verified") is True
        ),
        planning_input_file_sha256=current_source_file_sha256,
        board_calibration_sha256=(
            board_observation.get("calibration_sha256")
            if isinstance(board_observation, dict) else None
        ),
        current_calibration_sha256=current_calibration_sha256,
        shooter_detection=evidence_bundle["shooter_detection"],
        shooter_capture_config=evidence_bundle["shooter_capture_config"],
    )

    if errors:
        print("Planner skipped: game state has validation errors.")
        move = None
    elif (
        resource_manager.can_process("ANALYSE")
        and planner_gate["evidence_gate_passed"]
    ):
        move = planner.plan_next_move(
            state,
            planning_report=planning_report,
            identity_audit=identity_report,
            candidate_report=candidate_report,
            snapshot_report=synchronized_snapshot,
            current_source_file_sha256=current_source_file_sha256,
            current_calibration_sha256=current_calibration_sha256,
            current_identity_audit=identity_report,
            current_board_observation=board_observation,
        )
    else:
        move = None
        print("Planner skipped: current screenshot/provenance gate did not pass.")

    print("Recommended candidate:", move)
    if move is None:
        print("No currently valid selection candidate.")
    else:
        print("Candidate only; not an instruction to tap.")
    resource_manager.stop()
    print("Resource manager after analysis:", resource_manager.status())

    section("LEARNING ENGINE")
    learner = Learner()
    try:
        print("Shooting confidence:", learner.confidence("shooting"))
        print("Recent recorded observations:")
        history = learner.history(limit=5)
        if history:
            for item in history:
                print(item)
        else:
            print("No previous observations.")
    finally:
        learner.close()

    section("AUTOMATION READINESS")
    checks = {
        "Board dimensions correct": state.width == 35 and state.height == 35,
        "Observed cell count correct": state.remaining_pixels == 1225,
        "Game state valid": not errors,
        "Vision occupancy verified": vision_verified.get(
            "vision_occupancy_verified", False
        ),
        "Colour classification verified": vision_verified.get(
            "colour_classification_verified", False
        ),
        "Colour mappings verified": getattr(
            state, "colour_mappings_verified", False
        ),
        "At least one accessible shooter": bool(state.accessible_shooters()),
        "Real game taps enabled": GAME_TAPS_ENABLED,
    }
    for name, passed in checks.items():
        print(f"{'[PASS]' if passed else '[PENDING]'} {name}")

    print("\nDIAGNOSTIC COMPLETE")
    print("No game actions were performed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Slime AI diagnostics")
    parser.add_argument(
        "--observation",
        help="Use the latest screenshot-ingestor JSON instead of the legacy board baseline",
    )
    parser.add_argument(
        "--shooters",
        default="data/shooter_detection.json",
        help="Shooter detector JSON (used with --observation)",
    )
    parser.add_argument("--level", type=int, default=39)
    args = parser.parse_args()

    try:
        run_diagnostics(
            observation_path=args.observation,
            shooter_path=args.shooters if args.observation else None,
            level=args.level,
        )
    except Exception as error:
        print("\nDIAGNOSTIC FAILED")
        print(type(error).__name__ + ":", error)
        raise
