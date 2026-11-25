#!/usr/bin/env python3
import argparse
import json
import math
from pathlib import Path

from screenshot_ingestor import extract_board, sample_centres_for_grid

THRESHOLD = 35.0
STABILITY_THRESHOLD = 20.0
CALIBRATION = Path("data/vision_level39.json")


def _is_finite_number(value):
    """Treat exact integers as finite without float-conversion overflow."""
    if type(value) is int:
        return True
    return type(value) is float and math.isfinite(value)


def distance(a, b):
    return math.sqrt(sum((a[i] - b[i]) ** 2 for i in range(3)))


def _valid_rgb(sample):
    return (
        isinstance(sample, list) and len(sample) == 3
        and all(type(value) is int and 0 <= value <= 255
                for value in sample)
    )


def persistent_transition(baseline, first, second,
                          threshold=THRESHOLD,
                          stability=STABILITY_THRESHOLD):
    if any(not isinstance(item, dict) for item in (baseline, first, second)):
        raise ValueError("Each observation must be a JSON object")

    for key in ("image_size", "grid_size", "bounds"):
        if baseline.get(key) != first.get(key) or baseline.get(key) != second.get(key):
            raise ValueError(f"Incompatible {key}")

    grid_size = baseline.get("grid_size")
    if (not isinstance(grid_size, list) or len(grid_size) != 2
            or any(type(value) is not int or value < 1 for value in grid_size)
            or grid_size[0] > 10_000 or grid_size[1] > 10_000
            or grid_size[0] * grid_size[1] > 1_000_000):
        raise ValueError("Invalid grid_size")
    image_size = baseline.get("image_size")
    if (not isinstance(image_size, list) or len(image_size) != 2
            or any(type(value) is not int or value < 1 for value in image_size)):
        raise ValueError("Invalid image_size")
    bounds = baseline.get("bounds")
    if (not isinstance(bounds, list) or len(bounds) != 4
            or any(not _is_finite_number(value) for value in bounds)):
        raise ValueError("Invalid board bounds")
    image_width, image_height = image_size
    left, top, right, bottom = bounds
    if (left < 1 or top < 1 or right <= left or bottom <= top
            or right > image_width - 1 or bottom > image_height - 1):
        raise ValueError("Board bounds must be ordered and inside the screenshot")
    sample_centres = sample_centres_for_grid(grid_size, bounds)
    x_centres, y_centres = sample_centres["x"], sample_centres["y"]
    if (any(b - a < 3 for a, b in zip(x_centres, x_centres[1:]))
            or any(b - a < 3 for a, b in zip(y_centres, y_centres[1:]))):
        raise ValueError("Grid sample windows overlap")

    if (not _is_finite_number(threshold) or threshold < 0
            or not _is_finite_number(stability) or stability < 0):
        raise ValueError("Thresholds must be finite non-negative numbers")

    boards = [x.get("raw_rgb") for x in (baseline, first, second)]
    if any(not isinstance(board, list) or not board for board in boards):
        raise ValueError("Missing RGB grids")

    rows = len(boards[0])
    cols = len(boards[0][0])

    for board in boards:
        if len(board) != rows or any(
            not isinstance(row, list) or len(row) != cols for row in board
        ):
            raise ValueError("Invalid RGB grid dimensions")

    persistent = []
    transient = []

    for r in range(rows):
        for c in range(cols):
            a, b, d = boards[0][r][c], boards[1][r][c], boards[2][r][c]

            if not all(_valid_rgb(sample) for sample in (a, b, d)):
                raise ValueError("Invalid RGB sample")

            change1 = distance(a, b)
            change2 = distance(a, d)
            frame_difference = distance(b, d)

            if change1 >= threshold or change2 >= threshold:
                item = {
                    "row": r,
                    "column": c,
                    "baseline_rgb": a,
                    "first_rgb": b,
                    "second_rgb": d,
                    "baseline_to_first": round(change1, 2),
                    "baseline_to_second": round(change2, 2),
                    "frame_difference": round(frame_difference, 2),
                    "edge": r in (0, rows - 1) or c in (0, cols - 1),
                }

                if (
                    change1 >= threshold
                    and change2 >= threshold
                    and frame_difference <= stability
                ):
                    persistent.append(item)
                else:
                    transient.append(item)

    interior = [x for x in persistent if not x["edge"]]
    edge = [x for x in persistent if x["edge"]]

    return {
        "persistent_changes": len(persistent),
        "persistent_interior_changes": len(interior),
        "persistent_edge_changes": len(edge),
        "transient_or_unstable_changes": len(transient),
        "persistent": persistent,
        "transient": transient,
        "status": (
            "NO_PERSISTENT_CHANGE" if not persistent
            else "PERSISTENT_INTERIOR_CANDIDATES" if interior
            else "PERSISTENT_EDGE_CHANGES_ONLY"
        ),
        "persistent_changes_are_candidates_only": True,
        "tile_removals_verified": False,
        "board_transition_verified": False,
        "game_taps_enabled": False,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("baseline")
    parser.add_argument("first")
    parser.add_argument("second")
    parser.add_argument("--threshold", type=float, default=THRESHOLD)
    parser.add_argument("--stability", type=float, default=STABILITY_THRESHOLD)
    parser.add_argument("--output", default="data/persistent_transition_latest.json")
    args = parser.parse_args()

    if args.threshold < 0 or args.stability < 0:
        raise ValueError("Thresholds cannot be negative")

    calibration = json.loads(CALIBRATION.read_text())
    observations = [
        extract_board(path, calibration)
        for path in (args.baseline, args.first, args.second)
    ]

    report = persistent_transition(
        *observations,
        threshold=args.threshold,
        stability=args.stability,
    )
    report["input_images"] = [args.baseline, args.first, args.second]

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(json.dumps(report, indent=2))
    temporary.replace(output)

    print("SLIME AI — PERSISTENT TRANSITION AUDIT")
    print("=" * 48)
    print("Status:", report["status"])
    print("Persistent changes:", report["persistent_changes"])
    print("Persistent interior:", report["persistent_interior_changes"])
    print("Persistent edge:", report["persistent_edge_changes"])
    print("Transient/unstable:", report["transient_or_unstable_changes"])
    print("Tile removals verified: False")
    print("Board transition verified: False")
    print("Game taps enabled: False")
    print("Report:", output)


if __name__ == "__main__":
    main()
