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

    # Load either the legacy baseline or an explicit screenshot observation.
    section("LEVEL LOADING")
    state, vision_verified = load_level(
        level=level,
        observation_path=observation_path,
        shooter_path=shooter_path,
    )

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
    def read_evidence(filename):
        path = PROJECT_DIR / "data" / filename
        try:
            value = json.loads(path.read_text())
            return value if isinstance(value, dict) else None
        except (OSError, json.JSONDecodeError):
            return None

    planning_report = read_evidence("planning_gate_latest.json")
    identity_report = read_evidence("identity_audit_report.json")
    candidate_report = read_evidence("conveyor_identity_candidates.json")
    snapshot_report = read_evidence("snapshot_sync_report.json")

    print("Planning report present:", planning_report is not None)
    print("Identity report present:", identity_report is not None)
    print("Candidate report present:", candidate_report is not None)
    print("Snapshot report present:", snapshot_report is not None)

    if errors:
        print("Planner skipped: game state has validation errors.")
        move = None
    elif (
        resource_manager.can_process("ANALYSE")
        and vision_verified.get("shooter_capture_provenance_verified") is True
    ):
        move = planner.plan_next_move(
            state,
            planning_report=planning_report,
            identity_audit=identity_report,
            candidate_report=candidate_report,
            snapshot_report=snapshot_report,
        )
    else:
        move = None
        if vision_verified.get("shooter_capture_provenance_verified") is not True:
            print("Planner skipped: shooter panel is not bound to this board capture.")

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
