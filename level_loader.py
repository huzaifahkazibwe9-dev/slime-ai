import json
from pathlib import Path

from game_state import GameState
from shooter_loader import load_shooters
from board_loader import load_board


def load_level(level=39, observation_path=None, shooter_path=None):
    # Explicit screenshot mode consumes the latest ingested observation.
    # The legacy baseline loader remains the default for compatibility.
    if observation_path is not None:
        from screenshot_observation_loader import load_observed_level

        return load_observed_level(
            observation_path=observation_path,
            shooter_path=shooter_path or Path("data/shooter_detection.json"),
            level=level,
        )

    vision_path = Path("data/vision_level39.json")
    mapping_path = Path("data/color_matches.json")

    with vision_path.open() as f:
        vision = json.load(f)

    with mapping_path.open() as f:
        colour_data = json.load(f)

    board_data = load_board(vision_path)
    board = board_data["board"]

    if board_data["width"] != 35:
        raise ValueError("Unexpected board width")

    if board_data["height"] != 35:
        raise ValueError("Unexpected board height")

    shooters = load_shooters()

    state = GameState(
        board=board,
        shooters=shooters,
        level=level
    )

    state.colour_mappings = colour_data["mappings"]
    state.colour_mappings_verified = colour_data[
        "verified_by_gameplay"
    ]
    state.snapshot_id = vision.get("snapshot_id")
    state.capture_session_id = vision.get("capture_session_id")
    state.timestamp_identified = vision.get("timestamp_identified") is True

    audit = {
        "initial_occupancy_user_confirmed":
            board_data["initial_occupancy_user_confirmed"],
        "occupied_pixels": board_data["occupied_pixels"],
        "vision_occupancy_verified":
            vision["occupancy"]["verified"],
        "colour_classification_verified":
            board_data["colour_classification_verified"],
        "colour_mappings_gameplay_verified":
            state.colour_mappings_verified
    }

    return state, audit


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Load Slime Loop level data")
    parser.add_argument("--level", type=int, default=39)
    parser.add_argument(
        "--observation",
        help="Use data produced by screenshot_ingestor.py instead of the legacy vision baseline",
    )
    parser.add_argument(
        "--shooters",
        default="data/shooter_detection.json",
        help="Shooter detection JSON (used with --observation)",
    )
    args = parser.parse_args()

    state, audit = load_level(
        level=args.level,
        observation_path=args.observation,
        shooter_path=args.shooters,
    )

    print("UNIFIED LEVEL LOADER AUDIT")
    print("==========================")
    print("Level:", state.level)
    print("Board:", state.width, "x", state.height)
    print("Observed cells:", state.remaining_pixels)
    print("Shooters:", len(state.shooters))

    print("\nVERIFICATION STATUS")
    for name, value in audit.items():
        print(f"{name}: {value}")

    print("\nSHOOTER COLOUR MAPPINGS")
    mappings = getattr(state, "colour_mappings", {})
    if mappings:
        for shooter_id, mapping in mappings.items():
            print(
                shooter_id,
                "->",
                mapping["board_colour"],
                "|",
                mapping["status"]
            )
    else:
        print("No verified shooter-to-board colour mappings loaded.")

    errors = state.validate()
    print("\nGAME STATE VALIDATION:", errors)

    if errors:
        raise SystemExit("Level integration failed.")

    if audit.get("source") == "screenshot_observation":
        print("\nSCREENSHOT OBSERVATION INTEGRATION PASSED")
        print("Candidate state only; visual truth remains unverified.")
        print("Gameplay verification: False")
        print("Game taps enabled: False")
    else:
        assert state.width == 35
        assert state.height == 35
        assert state.remaining_pixels == 1225
        assert audit["occupied_pixels"] == 1225
        assert audit["initial_occupancy_user_confirmed"] is True
        assert len(state.shooters) == 4
        assert len(state.colour_mappings) == 4
        print("\nLEVEL INTEGRATION PASSED")
        print("All 1,225 starting tiles preserved.")
        print("Unverified colour mappings remain explicitly unverified.")
