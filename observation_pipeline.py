#!/usr/bin/env python3
import argparse
import hashlib
import json
from strict_json import strict_json_loads
from pathlib import Path

from screenshot_ingestor import extract_board
from edge_change_guard import inspect_edge_changes

BASELINE = Path("data/vision_level39.json")
REPORT = Path("data/observation_transition_latest.json")


def evaluate_observations(previous, current):
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
        return {
            "status": "REJECTED_INCOMPATIBLE_OBSERVATIONS",
            "errors": errors,
            "changed_cells": 0,
            "transition_verified": False,
            "tile_removals_verified": False,
            "game_taps_enabled": False,
        }

    try:
        guard = inspect_edge_changes(old_board, new_board)
    except (TypeError, ValueError, IndexError) as exc:
        return {
            "status": "REJECTED_INVALID_BOARD",
            "errors": [str(exc)],
            "changed_cells": 0,
            "transition_verified": False,
            "tile_removals_verified": False,
            "game_taps_enabled": False,
        }

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
    extracted = extract_board(path, calibration)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
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
