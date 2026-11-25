import json
from pathlib import Path
from collections import Counter

VISION_FILE = Path("data/vision_level39.json")
CONFIDENCE_FILE = Path("data/edge_confidence_latest.json")


def load_board(path=VISION_FILE, confidence_path=CONFIDENCE_FILE,
               data=None, confidence_data=None):
    if data is None:
        data = json.loads(Path(path).read_text())

    grid_size = data.get("grid_size")
    if (not isinstance(grid_size, list) or len(grid_size) != 2
            or any(type(value) is not int or value < 1
                   for value in grid_size)):
        raise ValueError("Invalid board grid dimensions")
    width, height = grid_size
    source_board = data.get("board")
    if not isinstance(source_board, list):
        raise ValueError("Invalid board data")
    occupancy = data.get("occupancy", {})
    if not isinstance(occupancy, dict):
        raise ValueError("Invalid occupancy metadata")
    mask = occupancy.get("mask")

    if len(source_board) != height:
        raise ValueError("Incorrect board height")

    if any(not isinstance(row, list) or len(row) != width
           for row in source_board):
        raise ValueError("Incorrect board width")

    if not isinstance(mask, list) or len(mask) != height:
        raise ValueError("Invalid occupancy mask height")

    if any(not isinstance(row, list) or len(row) != width for row in mask):
        raise ValueError("Invalid occupancy mask width")

    if any(type(value) is not int or value not in (0, 1)
           for row in mask for value in row):
        raise ValueError("Occupancy mask must contain only integer 0/1 values")

    occupied_count = sum(sum(row) for row in mask)

    if occupied_count != width * height:
        raise ValueError(
            f"Expected {width * height} occupied cells, "
            f"found {occupied_count}"
        )

    result = []

    for y in range(height):
        row = []

        for x in range(width):
            colour = source_board[y][x]

            if not isinstance(colour, str) or not colour:
                raise ValueError(
                    f"Invalid tile colour at ({x},{y})"
                )

            row.append(colour)

        result.append(row)

    # Load and validate confidence separately.
    if confidence_data is None:
        confidence_data = json.loads(
            Path(confidence_path).read_text()
        )
    if not isinstance(confidence_data, dict):
        raise ValueError("Invalid confidence report")

    if confidence_data.get("grid_size") != [height, width]:
        raise ValueError("Confidence grid dimensions do not match board")

    confidence_cells = confidence_data.get("cells")

    if not isinstance(confidence_cells, list):
        raise ValueError("Invalid confidence cell data")

    if len(confidence_cells) != height:
        raise ValueError("Incorrect confidence grid height")

    confidence_grid = []
    boundary_count = 0
    interior_count = 0

    for y in range(height):
        if not isinstance(confidence_cells[y], list):
            raise ValueError("Invalid confidence row")

        if len(confidence_cells[y]) != width:
            raise ValueError("Incorrect confidence grid width")

        confidence_row = []

        for x in range(width):
            cell = confidence_cells[y][x]
            if not isinstance(cell, dict):
                raise ValueError(f"Invalid confidence cell at ({x},{y})")

            if cell.get("row") != y or cell.get("column") != x:
                raise ValueError(
                    f"Confidence coordinate mismatch at ({x},{y})"
                )

            if cell.get("colour") != result[y][x]:
                raise ValueError(
                    f"Confidence colour mismatch at ({x},{y})"
                )

            boundary = (
                y == 0 or y == height - 1
                or x == 0 or x == width - 1
            )

            expected = (
                "requires_confirmation"
                if boundary else "provisional"
            )

            if cell.get("confidence") != expected:
                raise ValueError(
                    f"Unexpected confidence at ({x},{y})"
                )

            if cell.get("is_boundary") is not boundary:
                raise ValueError(
                    f"Boundary classification mismatch at ({x},{y})"
                )

            confidence_row.append(expected)

            if boundary:
                boundary_count += 1
            else:
                interior_count += 1

        confidence_grid.append(confidence_row)

    if confidence_data.get("all_cells_preserved") is not True:
        raise ValueError("Confidence report does not preserve all cells")

    return {
        "board": result,
        "confidence": confidence_grid,
        "width": width,
        "height": height,
        "candidate_pixels": width * height,
        "occupied_pixels": occupied_count,
        "boundary_cells_needing_confirmation": boundary_count,
        "interior_provisional_cells": interior_count,
        "confidence_available": True,
        "initial_occupancy_user_confirmed":
            occupancy.get("initial_occupancy_user_confirmed", False),
        "colour_classification_verified":
            occupancy.get("colour_classification_verified", False),
        "tile_removals_verified": False,
        "board_transition_verified": False,
        "game_taps_enabled": False,
        "verified": False
    }


if __name__ == "__main__":
    result = load_board()

    print("BOARD LOADER — BUILD 11F")
    print("=========================")
    print("Dimensions:", result["width"], "x", result["height"])
    print("Candidate pixels:", result["candidate_pixels"])
    print("Occupied pixels:", result["occupied_pixels"])
    print("Boundary confirmation required:",
          result["boundary_cells_needing_confirmation"])
    print("Interior provisional:",
          result["interior_provisional_cells"])
    print("Confidence available:", result["confidence_available"])
    print("Initial occupancy user-confirmed:",
          result["initial_occupancy_user_confirmed"])
    print("Colour classification verified:",
          result["colour_classification_verified"])
    print("Tile removals verified:", result["tile_removals_verified"])
    print("Board transition verified:", result["board_transition_verified"])
    print("Gameplay taps enabled:", result["game_taps_enabled"])

    counts = Counter(
        colour for row in result["board"] for colour in row
    )

    print("\nCOLOUR COUNTS")
    for colour, count in sorted(counts.items()):
        print(f"{colour:10} {count}")

    assert result["candidate_pixels"] == 1225
    assert result["occupied_pixels"] == 1225
    assert result["boundary_cells_needing_confirmation"] == 136
    assert result["interior_provisional_cells"] == 1089
    assert sum(counts.values()) == 1225
    assert all(
        cell is not None
        for row in result["board"]
        for cell in row
    )

    print("\nBUILD 11F BOARD LOADER PASSED")
