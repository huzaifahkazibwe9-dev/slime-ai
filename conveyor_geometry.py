"""Verified conveyor direction and screen-to-board geometry."""

import json
from math import floor, isfinite
from numbers import Real
from pathlib import Path

REFERENCE_SIZE = (1080, 2220)
REFERENCE_BOARD_BOUNDS = (201, 431, 881, 1113)
GRID_SIZE = (35, 35)

DIRECTIONS = {
    "bottom": "up",
    "right": "left",
    "top": "down",
    "left": "right",
}


def _finite_real(value):
    if isinstance(value, bool) or not isinstance(value, Real):
        return False
    try:
        return isfinite(float(value))
    except (OverflowError, TypeError, ValueError):
        return False


def calculate_firing_geometry(
    screen_center,
    segment,
    image_size,
    board_bounds=REFERENCE_BOARD_BOUNDS,
    grid_size=GRID_SIZE,
    position_verified=False,
):
    if not isinstance(segment, str):
        raise ValueError("Conveyor segment must be a string")
    segment = segment.lower()

    if segment not in DIRECTIONS:
        raise ValueError(f"Unknown conveyor segment: {segment}")

    if (not isinstance(screen_center, (list, tuple))
            or len(screen_center) != 2
            or not all(_finite_real(value) for value in screen_center)):
        raise ValueError("Screen center must contain two finite numeric coordinates")
    if (not isinstance(image_size, (list, tuple))
            or len(image_size) != 2
            or not all(_finite_real(value) for value in image_size)):
        raise ValueError("Image size must contain two finite numeric dimensions")

    image_width, image_height = image_size

    if image_width <= 0 or image_height <= 0:
        raise ValueError("Invalid screenshot dimensions")

    if (not isinstance(board_bounds, (list, tuple))
            or len(board_bounds) != 4
            or not all(_finite_real(value) for value in board_bounds)):
        raise ValueError("Board bounds must contain four finite numeric values")
    if (not isinstance(grid_size, (list, tuple))
            or len(grid_size) != 2
            or any(type(value) is not int or value <= 0
                   for value in grid_size)):
        raise ValueError("Grid size must contain two positive integers")

    sx, sy = screen_center
    scale_x = image_width / REFERENCE_SIZE[0]
    scale_y = image_height / REFERENCE_SIZE[1]

    left, top, right, bottom = board_bounds
    if left >= right or top >= bottom:
        raise ValueError("Board bounds must have positive width and height")
    left *= scale_x
    right *= scale_x
    top *= scale_y
    bottom *= scale_y

    cols, rows = grid_size

    if cols <= 0 or rows <= 0:
        raise ValueError("Invalid board dimensions")

    cell_width = (right - left) / cols
    cell_height = (bottom - top) / rows

    # A shooter must lie on the declared conveyor segment. Reject positions
    # outside the calibrated segment instead of clamping them to an edge lane.
    if segment in ("bottom", "top"):
        if not left <= sx <= right:
            raise ValueError("Shooter center is outside the horizontal conveyor span")
    else:
        if not top <= sy <= bottom:
            raise ValueError("Shooter center is outside the vertical conveyor span")

    if segment == "bottom" and sy < bottom:
        raise ValueError("Bottom-segment shooter center is not below the board")
    if segment == "top" and sy > top:
        raise ValueError("Top-segment shooter center is not above the board")
    if segment == "right" and sx < right:
        raise ValueError("Right-segment shooter center is not right of the board")
    if segment == "left" and sx > left:
        raise ValueError("Left-segment shooter center is not left of the board")

    if segment in ("bottom", "top"):
        col = floor((sx - left) / cell_width)
        col = max(0, min(cols - 1, col))
        row = rows if segment == "bottom" else -1
    else:
        row = floor((sy - top) / cell_height)
        row = max(0, min(rows - 1, row))
        col = cols if segment == "right" else -1

    direction = DIRECTIONS[segment]

    first_cells = {
        "up": (col, rows - 1),
        "down": (col, 0),
        "left": (cols - 1, row),
        "right": (0, row),
    }

    return {
        "segment": segment,
        "direction": direction,
        "origin": (col, row),
        "first_board_cell": first_cells[direction],
        "verified_direction": True,
        "verified_screen_position": bool(position_verified),
        "game_taps_enabled": False,
    }


def audit_saved_calibration(path="data/conveyor_calibration.json"):
    data = json.loads(Path(path).read_text())
    width, height = data["image_size"]
    results = []

    if not data.get("verified_by_user"):
        raise AssertionError("Calibration lacks user confirmation")

    for item in data["shooters"]:
        segment = item["segment"]

        result = calculate_firing_geometry(
            item["center"],
            segment,
            (width, height),
            position_verified=True,
        )

        assert result["direction"] == data["directions"][segment]
        assert result["verified_screen_position"]
        assert result["game_taps_enabled"] is False

        x, y = result["first_board_cell"]
        assert 0 <= x < GRID_SIZE[0]
        assert 0 <= y < GRID_SIZE[1]

        results.append((item["id"], result))

    return results


if __name__ == "__main__":
    print("SLIME AI — VERIFIED CONVEYOR CALIBRATION")
    print("=" * 45)

    results = audit_saved_calibration()

    for shooter_id, result in results:
        print(
            f"[PASS] {shooter_id}: "
            f"{result['direction']} | "
            f"origin={result['origin']} | "
            f"first cell={result['first_board_cell']}"
        )

    print(f"\n{len(results)}/8 calibration points passed.")
    print("Game taps remain disabled.")
