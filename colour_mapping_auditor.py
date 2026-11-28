import json
import math
from pathlib import Path
from collections import defaultdict
from statistics import median

BOARD_FILE = Path("data/vision_level39.json")
SHOOTER_FILE = Path("data/shooter_detection.json")
MAPPING_FILE = Path("data/color_matches.json")
OUTPUT_FILE = Path("data/colour_mapping_evidence.json")

def distance(a, b):
    return math.sqrt(sum((x-y)**2 for x, y in zip(a, b)))

def _valid_rgb(value):
    """Return True only for a length-3 sequence of finite numbers."""
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        return False
    for channel in value:
        if type(channel) is bool or not isinstance(channel, (int, float)):
            return False
        if not math.isfinite(channel):
            return False
    return True


def audit(board_data, shooter_data, mapping_data):
    board = board_data["board"]
    rgb = board_data["raw_rgb"]
    if not isinstance(board, list) or not isinstance(rgb, list) or len(board) != len(rgb):
        raise ValueError("board and raw_rgb must be equal-length lists")
    profiles = defaultdict(list)

    for y, row in enumerate(board):
        if not isinstance(row, list) or y >= len(rgb) or not isinstance(rgb[y], list) or len(row) != len(rgb[y]):
            raise ValueError(f"board row {y} and raw_rgb row {y} must be equal-length lists")
        for x, label in enumerate(row):
            sample = rgb[y][x]
            if not _valid_rgb(sample):
                raise ValueError(f"board RGB sample at ({y}, {x}) must be three finite numbers")
            profiles[label].append(sample)

    medians = {
        label: [median(channel) for channel in zip(*samples)]
        for label, samples in profiles.items()
    }

    results = []

    for shooter in shooter_data["visible_shooters"]:
        sid = shooter["id"]
        colour = shooter["color"]["name"]
        shooter_rgb = shooter["color"]["rgb"]
        if not _valid_rgb(shooter_rgb):
            raise ValueError(f"shooter {sid} RGB must be three finite numbers")

        rankings = sorted(
            [
                {
                    "board_colour": label,
                    "distance": round(distance(shooter_rgb, profile), 2),
                    "board_median_rgb": [round(v, 2) for v in profile],
                    "sample_count": len(profiles[label])
                }
                for label, profile in medians.items()
            ],
            key=lambda item: item["distance"]
        )

        existing = mapping_data["mappings"].get(sid, {})

        results.append({
            "shooter_id": sid,
            "shooter_colour": colour,
            "shooter_rgb": shooter_rgb,
            "existing_candidate": existing.get("board_colour"),
            "existing_status": existing.get("status"),
            "rankings": rankings,
            "best_candidate": rankings[0]["board_colour"],
            "best_distance": rankings[0]["distance"],
            "second_best_candidate": (
                rankings[1]["board_colour"] if len(rankings) > 1 else None
            ),
            "second_best_distance": (
                rankings[1]["distance"] if len(rankings) > 1 else None
            ),
            "distance_margin": (
                round(rankings[1]["distance"] - rankings[0]["distance"], 2)
                if len(rankings) > 1 else None
            ),
            "verified": False
        })

    return {
        "method": "per-channel median RGB profile with Euclidean distance",
        "board_dimensions": board_data["grid_size"],
        "board_colour_profiles": {
            label: {
                "median_rgb": [round(v, 2) for v in medians[label]],
                "sample_count": len(profiles[label])
            }
            for label in sorted(profiles)
        },
        "results": results,
        "gameplay_verified": False,
        "gameplay_taps_enabled": False,
        "warning": (
            "RGB proximity is visual evidence only. It does not prove "
            "gameplay colour identity, pixel reachability, or firing."
        )
    }

def main():
    board = json.loads(BOARD_FILE.read_text())
    shooters = json.loads(SHOOTER_FILE.read_text())
    mappings = json.loads(MAPPING_FILE.read_text())

    report = audit(board, shooters, mappings)
    OUTPUT_FILE.write_text(json.dumps(report, indent=2))

    print("SLIME AI — COLOUR MAPPING EVIDENCE")
    print("=" * 48)

    for item in report["results"]:
        print(f"\n{item['shooter_id']} — {item['shooter_colour']}")
        print("Existing candidate:", item["existing_candidate"])
        print("Fresh best candidate:", item["best_candidate"])
        print("Best distance:", item["best_distance"])
        print("Second candidate:", item["second_best_candidate"])
        print("Second distance:", item["second_best_distance"])
        print("Distance margin:", item["distance_margin"])
        print("Top three:")
        for candidate in item["rankings"][:3]:
            print(" ", candidate["board_colour"],
                  "distance=", candidate["distance"],
                  "samples=", candidate["sample_count"])

    print("\nGameplay verified: False")
    print("Gameplay taps enabled: False")
    print("Report:", OUTPUT_FILE)

if __name__ == "__main__":
    main()
