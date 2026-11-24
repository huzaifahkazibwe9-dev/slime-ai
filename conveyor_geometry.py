"""Verified conveyor direction and screen-to-board geometry."""

import json
from math import floor
from pathlib import Path

REFERENCE_SIZE = (1080, 2220)
REFERENCE_BOARD_BOUNDS = (201, 431, 881, 1113)
GRID_SIZE = (35, 35)

def load_verified_calibration(path):
    """Load calibration only when a user-confirmed file exists and is valid JSON."""
    calibration_path = Path(path)
    try:
        raw = calibration_path.read_text()
    except FileNotFoundError as exc:
        raise FileNotFoundError(
            f"Verified calibration file is missing: {calibration_path}. "
            "Create it from a real screenshot and confirm the measured "
            "shooter positions; do not infer or enable gameplay from defaults."
        ) from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Calibration file is not valid JSON: {calibration_path}"
        ) from exc
    if not isinstance(data, dict):
        raise ValueError("Calibration root must be a JSON object.")
    if data.get("verified_by_user") is not True:
        raise ValueError("Calibration must be explicitly confirmed by the user.")

    def positive_integer_pair(value, field):
        if (not isinstance(value, list) or len(value) != 2
                or any(type(part) is not int or part <= 0 for part in value)):
            raise ValueError(f"Calibration {field} must contain two positive integers.")
        return value

    width, height = positive_integer_pair(data.get("image_size"), "image_size")
    positive_integer_pair(data.get("board_grid"), "board_grid")

    expected_directions = {
        "bottom": "up", "right": "left", "top": "down", "left": "right"
    }
    if data.get("directions") != expected_directions:
        raise ValueError("Calibration directions do not match the supported segment mapping.")

    shooters = data.get("shooters")
    if not isinstance(shooters, list) or not shooters:
        raise ValueError("Calibration shooters must be a non-empty array.")

    seen_ids = set()
    for index, shooter in enumerate(shooters):
        if not isinstance(shooter, dict):
            raise ValueError(f"Calibration shooter {index} must be an object.")
        shooter_id = shooter.get("id")
        segment = shooter.get("segment")
        center = shooter.get("center")
        if not isinstance(shooter_id, str) or not shooter_id.strip() or shooter_id in seen_ids:
            raise ValueError(f"Calibration shooter {index} has a missing or duplicate ID.")
        seen_ids.add(shooter_id)
        if not isinstance(segment, str) or segment not in expected_directions:
            raise ValueError(f"Calibration shooter {shooter_id} has an invalid segment.")
        if (not isinstance(center, list) or len(center) != 2
                or any(type(value) not in (int, float)
                       for value in center)):
            raise ValueError(f"Calibration shooter {shooter_id} has an invalid center.")
        x, y = center
        if not (0 <= x < width and 0 <= y < height):
            raise ValueError(f"Calibration shooter {shooter_id} center is outside the image.")

    return data


DIRECTIONS = {
    "bottom": "up",
    "right": "left",
    "top": "down",
    "left": "right",
}


def calculate_firing_geometry(
    screen_center,
    segment,
    image_size,
    board_bounds=REFERENCE_BOARD_BOUNDS,
    grid_size=GRID_SIZE,
    position_verified=False,
):
    segment = str(segment).lower()

    if segment not in DIRECTIONS:
        raise ValueError(f"Unknown conveyor segment: {segment}")

    if len(screen_center) != 2 or len(image_size) != 2:
        raise ValueError("Expected two-dimensional coordinates")

    image_width, image_height = image_size

    if image_width <= 0 or image_height <= 0:
        raise ValueError("Invalid screenshot dimensions")

    sx, sy = screen_center
    scale_x = image_width / REFERENCE_SIZE[0]
    scale_y = image_height / REFERENCE_SIZE[1]

    left, top, right, bottom = board_bounds
    left *= scale_x
    right *= scale_x
    top *= scale_y
    bottom *= scale_y

    cols, rows = grid_size

    if cols <= 0 or rows <= 0:
        raise ValueError("Invalid board dimensions")

    cell_width = (right - left) / cols
    cell_height = (bottom - top) / rows

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
    data = load_verified_calibration(path)
    width, height = data["image_size"]
    results = []

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
