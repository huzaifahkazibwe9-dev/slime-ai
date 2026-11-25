#!/usr/bin/env python3
import argparse
import json
from strict_json import strict_json_loads
import math
from pathlib import Path

from screenshot_ingestor import extract_board

BASELINE = Path("data/vision_level39.json")
THRESHOLD = 35.0


def audit_rgb(previous, current, threshold=THRESHOLD):
    if previous.get("image_size") != current.get("image_size"):
        raise ValueError("Screenshot dimensions differ")

    if previous.get("grid_size") != current.get("grid_size"):
        raise ValueError("Grid dimensions differ")

    if previous.get("bounds") != current.get("bounds"):
        raise ValueError("Board calibration differs")

    old = previous.get("raw_rgb")
    new = current.get("raw_rgb")

    if not isinstance(old, list) or not isinstance(new, list):
        raise ValueError("Missing RGB samples")

    if len(old) != len(new) or not old:
        raise ValueError("RGB grid dimensions differ")

    rows = len(old)
    cols = len(old[0])

    if any(len(row) != cols for row in old + new):
        raise ValueError("RGB grids must be rectangular")

    changes = []

    for r in range(rows):
        for c in range(cols):
            a, b = old[r][c], new[r][c]

            if (
                not isinstance(a, list) or len(a) != 3
                or not isinstance(b, list) or len(b) != 3
            ):
                raise ValueError("Invalid RGB sample")

            distance = math.sqrt(
                sum((float(a[i]) - float(b[i])) ** 2 for i in range(3))
            )

            if distance >= threshold:
                edge = (
                    r == 0 or r == rows - 1
                    or c == 0 or c == cols - 1
                )
                changes.append({
                    "row": r,
                    "column": c,
                    "previous_rgb": a,
                    "current_rgb": b,
                    "distance": round(distance, 2),
                    "edge": edge,
                })

    edge_changes = [x for x in changes if x["edge"]]
    interior_changes = [x for x in changes if not x["edge"]]

    if not changes:
        status = "NO_SIGNIFICANT_RGB_CHANGE"
    elif not interior_changes:
        status = "EDGE_RGB_CHANGES_ONLY"
    else:
        status = "INTERIOR_RGB_CHANGES_DETECTED"

    return {
        "status": status,
        "threshold": threshold,
        "changed_cells": len(changes),
        "edge_changes": len(edge_changes),
        "interior_changes": len(interior_changes),
        "changes": changes,
        "visual_transition_verified": False,
        "tile_removals_verified": False,
        "game_taps_enabled": False,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("previous")
    parser.add_argument("current")
    parser.add_argument("--threshold", type=float, default=THRESHOLD)
    parser.add_argument("--output", default="data/rgb_transition_latest.json")
    args = parser.parse_args()

    if args.threshold < 0:
        raise ValueError("Threshold cannot be negative")

    calibration = strict_json_loads(BASELINE.read_text())

    previous = extract_board(args.previous, calibration)
    current = extract_board(args.current, calibration)

    report = audit_rgb(previous, current, args.threshold)
    report["previous_image"] = str(Path(args.previous))
    report["current_image"] = str(Path(args.current))

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(json.dumps(report, indent=2))
    temporary.replace(output)

    print("SLIME AI — RGB TRANSITION AUDIT")
    print("=" * 48)
    print("Status:", report["status"])
    print("Threshold:", report["threshold"])
    print("Changed cells:", report["changed_cells"])
    print("Edge changes:", report["edge_changes"])
    print("Interior changes:", report["interior_changes"])
    print("Visual transition verified: False")
    print("Tile removals verified: False")
    print("Game taps enabled: False")
    print("Report:", output)


if __name__ == "__main__":
    main()
