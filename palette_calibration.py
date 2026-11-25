import json
from strict_json import strict_json_loads
import numpy as np
from collections import defaultdict

with open("data/vision_level39.json") as f:
    vision = strict_json_loads(f.read())

with open("data/shooter_detection.json") as f:
    shooters = strict_json_loads(f.read())["visible_shooters"]

board = vision["board"]
rgb = np.array(vision["raw_rgb"], dtype=float)

BACKGROUND = {"cyan", "green"}
profiles = defaultdict(list)

for y, row in enumerate(board):
    for x, colour in enumerate(row):
        if True:
            profiles[colour].append(rgb[y, x])

print("SHOOTER TO FOREGROUND PALETTE CALIBRATION")
print("=" * 55)

for shooter in shooters:
    srgb = np.array(shooter["color"]["rgb"], dtype=float)
    distances = []

    for colour, samples in profiles.items():
        median = np.median(samples, axis=0)
        distance = float(np.linalg.norm(srgb - median))
        distances.append((distance, colour, median))

    distances.sort()

    print(f"\n{shooter['id']} | {shooter['color']['name']}")
    print("Shooter RGB:", srgb.astype(int).tolist())

    for distance, colour, median in distances[:3]:
        print(
            f"  {colour:8} distance={distance:.2f} "
            f"median={median.astype(int).tolist()}"
        )

print("\nCalibration is provisional, not gameplay-verified.")
