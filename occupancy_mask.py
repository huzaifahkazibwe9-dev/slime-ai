import json
from strict_json import strict_json_loads
from collections import Counter

with open("data/vision_level39.json") as f:
    board = strict_json_loads(f.read())["board"]

BACKGROUND = {"cyan", "green"}

mask = []
counts = Counter()

for row in board:
    mask_row = []

    for colour in row:
        occupied = colour not in BACKGROUND
        mask_row.append(1 if occupied else 0)

        if occupied:
            counts[colour] += 1

    mask.append(mask_row)

result = {
    "width": len(board[0]),
    "height": len(board),
    "background_candidates": sorted(BACKGROUND),
    "mask": mask,
    "foreground_counts": dict(counts),
    "foreground_total": sum(counts.values()),
    "verified": False
}

with open("data/occupancy_mask.json", "w") as f:
    json.dump(result, f, indent=2)

print("PROVISIONAL OCCUPANCY MASK")
print("Foreground cells:", result["foreground_total"])
print("Background candidates:", BACKGROUND)

for colour, count in sorted(counts.items()):
    print(f"{colour:10}: {count}")

print("\nSaved: data/occupancy_mask.json")
print("WARNING: Occupancy has not yet been verified against gameplay.")
