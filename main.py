from pathlib import Path
from collections import Counter
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


def run_diagnostics():
    section("SLIME AI CENTRAL DIAGNOSTIC")

    print("Project:", PROJECT_DIR)
    print("Game taps:", "ENABLED" if GAME_TAPS_ENABLED else "DISABLED")
    resource_manager = ResourceManager()
    section("LOW-POWER RESOURCE MANAGEMENT")
    print("Operating mode:", resource_manager.mode.value)
    print("Background loop:", resource_manager.status()["background_loop"])
    print("Timer running:", resource_manager.status()["timer_running"])
    print("Game taps enabled:", resource_manager.game_taps_enabled)


    # Load level data.
    section("LEVEL LOADING")

    state, vision_verified = load_level(level=39)

    print("Level:", state.level)
    print("Board dimensions:", state.width, "x", state.height)
    print("Starting tiles:", state.remaining_pixels)
    print("Shooters loaded:", len(state.shooters))
    print("Vision occupancy verified:", vision_verified)

    # Validate board and game state.
    section("GAME STATE VALIDATION")

    errors = state.validate()

    if errors:
        for error in errors:
            print("ERROR:", error)
    else:
        print("Game-state validation: PASSED")

    print("Conveyor free spaces:", state.conveyor_free)
    print("Storage free spaces:", state.storage_free)

    # Board colour distribution.
    section("BOARD COLOUR DISTRIBUTION")

    counts = Counter(
        pixel
        for row in state.board
        for pixel in row
    )

    for colour, count in sorted(counts.items()):
        print(f"{colour:12} {count}")

    # Shooter inspection.
    section("SHOOTER STATUS")

    for shooter_id, shooter in state.shooters.items():
        print(
            shooter_id,
            "| Colour:", shooter.color,
            "| Ammo:", shooter.ammo,
            "| Bonds:", shooter.bonded_ids,
            "| Accessible:", shooter.accessible,
            "| Position:", (shooter.x, shooter.y),
            "| Direction:", shooter.direction
        )

    print("Accessible shooters:", len(state.accessible_shooters()))

    # Colour mapping verification.
    section("COLOUR MAPPING STATUS")

    for shooter_id, mapping in state.colour_mappings.items():
        print(
            shooter_id,
            "->",
            mapping["board_colour"],
            "| Status:",
            mapping["status"]
        )

    print(
        "Mappings gameplay-verified:",
        state.colour_mappings_verified
    )

    # Planner diagnostic.
    section("PLANNER DIAGNOSTIC")
    resource_manager.set_mode("ANALYSE")


    if errors:
        print("Planner skipped: game state has validation errors.")
        move = None
    else:
        if resource_manager.can_process("ANALYSE"):
            move = planner.plan_next_move(state)
        else:
            move = None

    print("Recommended candidate:", move)

    if move is None:
        print("No currently valid selection candidate.")
    else:
        print("Candidate only; not an instruction to tap.")
    resource_manager.stop()
    print("Resource manager after analysis:", resource_manager.status())


    # Read learning data without adding test observations.
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

    # Final safety assessment.
    section("AUTOMATION READINESS")

    checks = {
        "Board dimensions correct": (
            state.width == 35 and state.height == 35
        ),
        "All starting tiles preserved": (
            state.remaining_pixels == 1225
        ),
        "Game state valid": not errors,
        "Vision verified": (
            vision_verified.get("vision_occupancy_verified", False)
            and vision_verified.get("colour_classification_verified", False)
        ),
        "Colour mappings verified": bool(
            state.colour_mappings_verified
        ),
        "At least one accessible shooter": bool(
            state.accessible_shooters()
        ),
        "Real game taps enabled": GAME_TAPS_ENABLED,
    }

    for name, passed in checks.items():
        print(f"{'[PASS]' if passed else '[PENDING]'} {name}")

    print("\nDIAGNOSTIC COMPLETE")
    print("No game actions were performed.")


if __name__ == "__main__":
    try:
        run_diagnostics()
    except Exception as error:
        print("\nDIAGNOSTIC FAILED")
        print(type(error).__name__ + ":", error)
        raise
