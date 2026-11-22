#!/usr/bin/env python3
import argparse
import json
import math
from pathlib import Path

from screenshot_ingestor import extract_board

THRESHOLD = 35.0
STABILITY_THRESHOLD = 20.0
CALIBRATION = Path("data/vision_level39.json")


def distance(a, b):
    return math.sqrt(sum((float(a[i]) - float(b[i])) ** 2 for i in range(3)))


def persistent_transition(baseline, first, second,
                          threshold=THRESHOLD,
                          stability=STABILITY_THRESHOLD):
    for key in ("image_size", "grid_size", "bounds"):
        if baseline.get(key) != first.get(key) or baseline.get(key) != second.get(key):
            raise ValueError(f"Incompatible {key}")

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

            if any(not isinstance(x, list) or len(x) != 3 for x in (a, b, d)):
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
