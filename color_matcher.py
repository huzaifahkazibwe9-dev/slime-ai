import json
from strict_json import strict_json_loads
import numpy as np
from pathlib import Path

BOARD_FILE = Path("data/vision_level39.json")
SHOOTER_FILE = Path("data/shooter_detection.json")
OUTPUT_FILE = Path("data/color_match_candidates.json")

THRESHOLD = 55.0

def rgb_distance(a, b):
    return float(np.linalg.norm(
        np.array(a, dtype=float) -
        np.array(b, dtype=float)
    ))

def main():
    with open(BOARD_FILE) as f:
        board_data = strict_json_loads(f.read())

    with open(SHOOTER_FILE) as f:
        shooter_data = strict_json_loads(f.read())

    rgb_grid = np.array(board_data["raw_rgb"], dtype=np.float32)
    rows, cols, _ = rgb_grid.shape

    print("BOARD:", rows, "x", cols)
    print("TOTAL CELLS:", rows * cols)

    results = []

    for shooter in shooter_data["visible_shooters"]:
        shooter_rgb = shooter["color"]["rgb"]

        distances = np.linalg.norm(
            rgb_grid - np.array(shooter_rgb, dtype=np.float32),
            axis=2
        )

        matches = np.argwhere(distances <= THRESHOLD)

        nearest = np.unravel_index(
            np.argmin(distances),
            distances.shape
        )

        result = {
            "shooter_id": shooter["id"],
            "color": shooter["color"]["name"],
            "shooter_rgb": shooter_rgb,
            "ammo": shooter["ammo"],
            "threshold": THRESHOLD,
            "matching_cells": int(len(matches)),
            "nearest_distance": round(
                float(distances[nearest]), 2
            ),
            "nearest_cell": {
                "row": int(nearest[0]),
                "column": int(nearest[1])
            },
            "sample_matches": [
                {
                    "row": int(y),
                    "column": int(x),
                    "distance": round(float(distances[y, x]), 2),
                    "board_rgb": [
                        int(v) for v in rgb_grid[y, x]
                    ]
                }
                for y, x in matches[:15]
            ],
            "confirmed_targets": False
        }

        results.append(result)

        print("\nSHOOTER:", shooter["id"])
        print("COLOUR:", shooter["color"]["name"])
        print("RGB:", shooter_rgb)
        print("AMMO:", shooter["ammo"])
        print("SIMILAR CELLS:", len(matches))
        print("NEAREST DISTANCE:", result["nearest_distance"])
        print("NEAREST CELL:", result["nearest_cell"])

    output = {
        "board_dimensions": [rows, cols],
        "matching_method": "RGB Euclidean distance",
        "threshold": THRESHOLD,
        "results": results,
        "warning": (
            "Colour similarity does not confirm pixel occupancy "
            "or shooter reachability."
        )
    }

    OUTPUT_FILE.write_text(json.dumps(output, indent=2))
    print("\nSaved:", OUTPUT_FILE)

if __name__ == "__main__":
    main()
