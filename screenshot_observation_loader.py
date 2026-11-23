#!/usr/bin/env python3
"""Load the latest screenshot observation into a conservative GameState.

This adapter deliberately keeps visual observations separate from gameplay
verification. It never marks colours, removals, shooter accessibility, or
live actions as verified.
"""
import argparse
import hashlib
import json
import math
from collections import Counter
from pathlib import Path

from game_state import GameState
from shooter_loader import load_shooters
from screenshot_ingestor import classify_rgb

DEFAULT_OBSERVATION = Path("data/board_observation_latest.json")
DEFAULT_SHOOTERS = Path("data/shooter_detection.json")


def _require_grid(data):
    if not isinstance(data, dict):
        raise ValueError("Observation must be a JSON object")

    grid = data.get("grid_size")
    image = data.get("image_size")
    bounds = data.get("bounds")
    board = data.get("board")
    rgb = data.get("raw_rgb")

    if (not isinstance(grid, list) or len(grid) != 2
            or any(type(v) is not int or v < 1 for v in grid)):
        raise ValueError("Invalid grid_size; expected positive [columns, rows]")
    if (not isinstance(image, list) or len(image) != 2
            or any(type(v) is not int or v < 1 for v in image)):
        raise ValueError("Invalid image_size")
    if (not isinstance(bounds, list) or len(bounds) != 4
            or any(type(v) not in (int, float) or not math.isfinite(v)
                   for v in bounds)):
        raise ValueError("Invalid board bounds")

    width, height = grid
    image_width, image_height = image
    left, top, right, bottom = bounds
    if (left < 1 or top < 1 or right <= left or bottom <= top
            or right > image_width - 1 or bottom > image_height - 1):
        raise ValueError("Board bounds are outside the screenshot")

    if not isinstance(board, list) or len(board) != height:
        raise ValueError("Board row count does not match grid_size")
    if not isinstance(rgb, list) or len(rgb) != height:
        raise ValueError("RGB row count does not match grid_size")

    counts = Counter()
    for y in range(height):
        if not isinstance(board[y], list) or len(board[y]) != width:
            raise ValueError(f"Board row {y} has incorrect width")
        if not isinstance(rgb[y], list) or len(rgb[y]) != width:
            raise ValueError(f"RGB row {y} has incorrect width")
        for x in range(width):
            label = board[y][x]
            sample = rgb[y][x]
            if not isinstance(label, str) or not label:
                raise ValueError(f"Invalid colour label at ({x},{y})")
            if (not isinstance(sample, list) or len(sample) != 3
                    or any(type(v) is not int or v < 0 or v > 255
                           for v in sample)):
                raise ValueError(f"Invalid RGB sample at ({x},{y})")
            if classify_rgb(sample) != label:
                raise ValueError(
                    f"RGB/classification mismatch at ({x},{y}): "
                    f"saved={label}, recalculated={classify_rgb(sample)}"
                )
            counts[label] += 1

    if data.get("counts") != dict(counts):
        raise ValueError("Saved colour counts do not match board labels")

    digest = data.get("source_sha256")
    snapshot_id = data.get("snapshot_id")
    if (not isinstance(digest, str) or len(digest) != 64
            or any(c not in "0123456789abcdef" for c in digest.lower())
            or snapshot_id != "sha256:" + digest):
        raise ValueError("Invalid or inconsistent screenshot snapshot identity")

    if data.get("gameplay_verified") is not False:
        raise ValueError("Screenshot observation must remain gameplay-unverified")
    if data.get("vision_classification_verified") is not False:
        raise ValueError("Screenshot colours must remain unverified")
    if data.get("game_taps_enabled") is not False:
        raise ValueError("Live game actions must remain disabled")

    return width, height, board, counts


def load_observed_level(
    observation_path=DEFAULT_OBSERVATION,
    shooter_path=DEFAULT_SHOOTERS,
    level=39,
):
    observation_path = Path(observation_path)
    shooter_path = Path(shooter_path)
    data = json.loads(observation_path.read_text())
    width, height, board, counts = _require_grid(data)

    shooters = load_shooters(shooter_path)
    state = GameState(
        board=[row[:] for row in board],
        shooters=shooters,
        level=level,
    )
    # Preserve the legacy diagnostic interface without inventing mappings.
    state.colour_mappings = {}
    state.colour_mappings_verified = False
    errors = state.validate()
    if errors:
        raise ValueError("Invalid integrated game state: " + "; ".join(errors))

    audit = {
        "source": "screenshot_observation",
        "snapshot_id": data["snapshot_id"],
        "image_size": data["image_size"],
        "grid_size": [width, height],
        "board_cells": width * height,
        "colour_counts": dict(sorted(counts.items())),
        "classification_consistent_with_extractor": True,
        "colour_truth_verified": False,
        "shooter_count": len(shooters),
        "shooter_panel_positions_only": True,
        "shooter_positions_gameplay_verified": False,
        "initial_occupancy_confirmed": False,
        "vision_occupancy_verified": False,
        "colour_classification_verified": False,
        "vision_classification_verified": False,
        "colour_mapping_verified": False,
        "board_transition_verified": False,
        "gameplay_verified": False,
        "game_taps_enabled": False,
    }
    return state, audit


def main():
    parser = argparse.ArgumentParser(
        description="Integrate the latest screenshot observation with detected shooters"
    )
    parser.add_argument("--observation", default=str(DEFAULT_OBSERVATION))
    parser.add_argument("--shooters", default=str(DEFAULT_SHOOTERS))
    parser.add_argument("--level", type=int, default=39)
    args = parser.parse_args()

    state, audit = load_observed_level(
        args.observation, args.shooters, args.level
    )
    print("SLIME AI — SCREENSHOT-TO-GAME-STATE INTEGRATION")
    print("=" * 54)
    print("Level:", state.level)
    print("Board:", state.width, "x", state.height)
    print("Observed cells:", state.remaining_pixels)
    print("Shooters:", len(state.shooters))
    print("Snapshot:", audit["snapshot_id"])
    print("State validation:", state.validate())
    print("\nEVIDENCE STATUS")
    for key, value in audit.items():
        print(f"{key}: {value}")
    print("\nINTEGRATION PASSED")
    print("This is a candidate state, not a gameplay-verified state.")
    print("Game taps enabled: False")


if __name__ == "__main__":
    main()
