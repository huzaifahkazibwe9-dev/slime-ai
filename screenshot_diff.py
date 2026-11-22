#!/usr/bin/env python3
"""Read-only comparison of two Slime Loop board screenshots."""

import json
import sys
from pathlib import Path
from PIL import Image
from statistics import median

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "data" / "screenshot_diff_latest.json"

REFERENCE_SIZE = (1080, 2220)
REFERENCE_BOUNDS = (201, 431, 881, 1113)
COLS = 35
ROWS = 35

# Ignore small rendering and compression differences.
CHANGE_THRESHOLD = 25


def board_geometry(image):
    width, height = image.size
    sx = width / REFERENCE_SIZE[0]
    sy = height / REFERENCE_SIZE[1]

    left, top, right, bottom = REFERENCE_BOUNDS

    return (
        left * sx,
        top * sy,
        right * sx,
        bottom * sy,
    )


def cell_sample(image, bounds, col, row):
    left, top, right, bottom = bounds

    cw = (right - left) / COLS
    ch = (bottom - top) / ROWS

    x0 = int(left + col * cw)
    x1 = int(left + (col + 1) * cw)
    y0 = int(top + row * ch)
    y1 = int(top + (row + 1) * ch)

    # Sample the central 40% of the tile to reduce edge effects.
    px0 = x0 + int((x1 - x0) * 0.30)
    px1 = x0 + int((x1 - x0) * 0.70)
    py0 = y0 + int((y1 - y0) * 0.30)
    py1 = y0 + int((y1 - y0) * 0.70)

    pixels = list(
        image.crop((px0, py0, px1, py1)).getdata()
    )

    if not pixels:
        raise ValueError("Empty tile sample.")

    return tuple(
        median(pixel[channel] for pixel in pixels)
        for channel in range(3)
    )


def colour_difference(a, b):
    return sum(abs(a[i] - b[i]) for i in range(3)) / 3


def compare(before_path, after_path):
    before = Image.open(before_path).convert("RGB")
    after = Image.open(after_path).convert("RGB")

    if before.size != after.size:
        raise ValueError(
            f"Screenshot dimensions differ: "
            f"{before.size} versus {after.size}"
        )

    bounds = board_geometry(before)

    if bounds[2] > before.width or bounds[3] > before.height:
        raise ValueError("Calibrated board bounds exceed screenshot.")

    changes = []

    for row in range(ROWS):
        for col in range(COLS):
            old = cell_sample(before, bounds, col, row)
            new = cell_sample(after, bounds, col, row)

            difference = colour_difference(old, new)

            if difference >= CHANGE_THRESHOLD:
                changes.append({
                    "cell": [col, row],
                    "difference": round(difference, 2),
                    "before_rgb": [round(v) for v in old],
                    "after_rgb": [round(v) for v in new],
                })

    return {
        "before": str(before_path),
        "after": str(after_path),
        "image_size": list(before.size),
        "board_grid": [COLS, ROWS],
        "threshold": CHANGE_THRESHOLD,
        "changed_cell_count": len(changes),
        "changed_cells": changes,
        "interpretation": "candidate_visual_changes_only",
        "actual_firing_verified": False,
        "gameplay_access_enabled": False,
    }


def main():
    if len(sys.argv) != 3:
        print("Usage:")
        print("python screenshot_diff.py BEFORE.jpg AFTER.jpg")
        return

    before = Path(sys.argv[1]).expanduser()
    after = Path(sys.argv[2]).expanduser()

    if not before.is_file() or not after.is_file():
        raise FileNotFoundError("One or both screenshot files were not found.")

    report = compare(before, after)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, indent=2))

    print("\nSLIME AI — SCREENSHOT DIFFERENCE")
    print("=" * 46)
    print("Before:", before)
    print("After: ", after)
    print("Changed candidate cells:", report["changed_cell_count"])

    for item in report["changed_cells"]:
        print(
            f"Cell {item['cell']} "
            f"difference={item['difference']}"
        )

    print("\nReport:", OUTPUT)
    print("These are visual candidates, not confirmed shots.")
    print("Actual firing verified: NO")
    print("Gameplay access enabled: NO")


if __name__ == "__main__":
    main()
