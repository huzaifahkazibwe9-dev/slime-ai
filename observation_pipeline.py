#!/usr/bin/env python3
import argparse
import hashlib
import json
import math
from strict_json import strict_json_loads
from pathlib import Path

from screenshot_ingestor import (
    COLOUR_LABELS,
    extract_board_bytes,
    validate_sample_window_geometry,
)
from edge_change_guard import inspect_edge_changes

BASELINE = Path("data/vision_level39.json")
REPORT = Path("data/observation_transition_latest.json")
VALID_BOARD_LABELS = frozenset(COLOUR_LABELS)


def _finite_number(value):
    """Match calibration number rules while excluding bool and non-finite floats."""
    if type(value) is int:
        return True
    return type(value) is float and math.isfinite(value)


def _observation_metadata_error(observation, name):
    """Validate screenshot dimensions and sampling bounds before comparison."""
    image_size = observation.get("image_size")
    if (
        not isinstance(image_size, list) or len(image_size) != 2
        or any(type(value) is not int or value < 1 for value in image_size)
    ):
        return f"{name} image_size must contain two positive integers"
    width, height = image_size

    grid_size = observation.get("grid_size")
    if not isinstance(grid_size, list) or len(grid_size) != 2:
        return f"{name} grid_size must be [columns, rows]"
    cols, rows = grid_size
    if (
        type(cols) is not int or type(rows) is not int
        or cols < 1 or rows < 1
    ):
        return f"{name} grid dimensions must be positive integers"
    if cols > 10_000 or rows > 10_000 or cols * rows > 1_000_000:
        return f"{name} grid dimensions exceed the safe sampling limit"

    bounds = observation.get("bounds")
    if (
        not isinstance(bounds, list) or len(bounds) != 4
        or any(not _finite_number(value) for value in bounds)
    ):
        return f"{name} bounds must contain four finite numeric coordinates"
    left, top, right, bottom = bounds
    if (
        left < 1 or top < 1 or right <= left or bottom <= top
        or right > width - 1 or bottom > height - 1
    ):
        return f"{name} bounds must be ordered and inside image_size"

    # Share the ingestor's exact rounded-centre and 3x3-window contract.
    try:
        validate_sample_window_geometry((cols, rows), bounds, (width, height))
    except (OverflowError, TypeError, ValueError) as exc:
        return f"{name} bounds and grid_size have invalid sampling geometry: {exc}"
    return None


def _board_grid_error(observation, name):
    """Return a diagnostic when board rows/columns disagree with calibration."""
    grid_size = observation.get("grid_size")
    if not isinstance(grid_size, list) or len(grid_size) != 2:
        return f"{name} grid_size must be [columns, rows]"

    cols, rows = grid_size
    if (
        type(cols) is not int or type(rows) is not int
        or cols < 1 or rows < 1
    ):
        return f"{name} grid dimensions must be positive integers"
    if cols > 10_000 or rows > 10_000 or cols * rows > 1_000_000:
        return f"{name} grid dimensions exceed the safe sampling limit"

    board = observation.get("board")
    if len(board) != rows:
        return (
            f"{name} board has {len(board)} rows but grid_size declares {rows}"
        )
    for row_index, row in enumerate(board):
        if not isinstance(row, list):
            return f"{name} board row {row_index} must be a list"
        if len(row) != cols:
            return (
                f"{name} board row {row_index} has {len(row)} columns "
                f"but grid_size declares {cols}"
            )
        for column_index, label in enumerate(row):
            if not isinstance(label, str) or label not in VALID_BOARD_LABELS:
                return (
                    f"{name} board cell ({row_index}, {column_index}) "
                    f"has an unknown colour label"
                )
    return None


def _rejected_observation(status, errors):
    return {
        "status": status,
        "errors": errors,
        "changed_cells": 0,
        "transition_verified": False,
        "tile_removals_verified": False,
        "game_taps_enabled": False,
    }


def evaluate_observations(previous, current):
    if not isinstance(previous, dict) or not isinstance(current, dict):
        return _rejected_observation(
            "REJECTED_INVALID_OBSERVATION",
            ["Both observations must be JSON objects"],
        )

    metadata_errors = [
        error for error in (
            _observation_metadata_error(previous, "previous"),
            _observation_metadata_error(current, "current"),
        )
        if error is not None
    ]
    if metadata_errors:
        return _rejected_observation(
            "REJECTED_INVALID_OBSERVATION", metadata_errors
        )

    errors = []

    for key in ("image_size", "grid_size", "bounds"):
        if previous.get(key) != current.get(key):
            errors.append(f"{key} differs between screenshots")

    old_board = previous.get("board")
    new_board = current.get("board")

    if not isinstance(old_board, list) or not isinstance(new_board, list):
        errors.append("Missing board data")
    elif not old_board or not new_board:
        errors.append("Empty board data")

    if errors:
        return _rejected_observation(
            "REJECTED_INCOMPATIBLE_OBSERVATIONS", errors
        )

    shape_errors = [
        error for error in (
            _board_grid_error(previous, "previous"),
            _board_grid_error(current, "current"),
        )
        if error is not None
    ]
    if shape_errors:
        return _rejected_observation("REJECTED_INVALID_BOARD", shape_errors)

    try:
        guard = inspect_edge_changes(old_board, new_board)
    except (TypeError, ValueError, IndexError) as exc:
        return _rejected_observation("REJECTED_INVALID_BOARD", [str(exc)])

    status = guard["status"]

    if status == "UNCHANGED":
        result_status = "NO_BOARD_CHANGE"
    elif status == "SUSPICIOUS_EDGE_ONLY_CHANGE":
        result_status = "REJECTED_SUSPICIOUS_EDGE_CHANGE"
    elif status == "INTERIOR_CHANGE_REQUIRES_VALIDATION":
        result_status = "INTERIOR_CHANGE_NEEDS_REVIEW"
    else:
        result_status = "EDGE_CHANGE_NEEDS_REVIEW"

    return {
        "status": result_status,
        "errors": [],
        "changed_cells": guard["changed_cells"],
        "edge_changes": guard["edge_changes"],
        "interior_changes": guard["interior_changes"],
        "replacement_counts": guard["replacement_counts"],
        "changes": guard["changes"],
        "transition_verified": False,
        "tile_removals_verified": False,
        "game_taps_enabled": False,
        "note": (
            "Colour changes are observations, not proof of tile removal. "
            "No cells are converted to empty automatically."
        ),
    }


def load_observation(path, calibration):
    path = Path(path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(path)

    # Bind both pixel extraction and provenance to exactly the same bytes.
    # Reopening the path after extraction could hash a replacement screenshot.
    image_bytes = path.read_bytes()
    digest = hashlib.sha256(image_bytes).hexdigest()
    extracted = extract_board_bytes(image_bytes, calibration)
    return {
        **extracted,
        "source": str(path),
        "sha256": digest,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Conservatively compare two Slime Loop screenshots"
    )
    parser.add_argument("previous")
    parser.add_argument("current")
    parser.add_argument("--baseline", default=str(BASELINE))
    parser.add_argument("--output", default=str(REPORT))
    args = parser.parse_args()

    calibration = strict_json_loads(Path(args.baseline).read_text())
    previous = load_observation(args.previous, calibration)
    current = load_observation(args.current, calibration)

    result = evaluate_observations(previous, current)
    result["previous_source"] = previous["source"]
    result["current_source"] = current["source"]
    result["previous_sha256"] = previous["sha256"]
    result["current_sha256"] = current["sha256"]

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(json.dumps(result, indent=2))
    temporary.replace(output)

    print("SLIME AI — SCREENSHOT TRANSITION PIPELINE")
    print("=" * 52)
    print("Previous:", Path(args.previous).name)
    print("Current:", Path(args.current).name)
    print("Status:", result["status"])
    print("Changed cells:", result["changed_cells"])
    print("Edge changes:", result.get("edge_changes", 0))
    print("Interior changes:", result.get("interior_changes", 0))
    print("Transition verified:", result["transition_verified"])
    print("Tile removals verified:", result["tile_removals_verified"])
    print("Game taps enabled:", result["game_taps_enabled"])
    print("Report:", output)


if __name__ == "__main__":
    main()
