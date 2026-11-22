import json
from pathlib import Path

from game_state import GameState
from shooter_loader import load_shooters
from board_loader import load_board


def load_level(level=39):
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
    state, audit = load_level()

    print("UNIFIED LEVEL LOADER AUDIT")
    print("==========================")
    print("Level:", state.level)
    print("Board:", state.width, "x", state.height)
    print("Remaining pixels:", state.remaining_pixels)
    print("Shooters:", len(state.shooters))

    print("\nVERIFICATION STATUS")
    for name, value in audit.items():
        print(f"{name}: {value}")

    print("\nSHOOTER COLOUR MAPPINGS")
    for shooter_id, mapping in state.colour_mappings.items():
        print(
            shooter_id,
            "->",
            mapping["board_colour"],
            "|",
            mapping["status"]
        )

    print("\nGAME STATE VALIDATION:", state.validate())

    assert state.width == 35
    assert state.height == 35
    assert state.remaining_pixels == 1225
    assert audit["occupied_pixels"] == 1225
    assert audit["initial_occupancy_user_confirmed"] is True
    assert len(state.shooters) == 4
    assert len(state.colour_mappings) == 4
    assert state.validate() == []

    print("\nLEVEL INTEGRATION PASSED")
    print("All 1,225 starting tiles preserved.")
    print("Unverified colour mappings remain explicitly unverified.")
