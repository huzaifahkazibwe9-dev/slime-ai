import json
from collections import Counter
from pathlib import Path

path = Path("data/vision_level39.json")
data = json.loads(path.read_text())

board = data["board"]
rgb = data["raw_rgb"]

assert len(board) == 35
assert all(len(row) == 35 for row in board)
assert all(len(row) == 35 for row in rgb)

print("VISION VALIDATION")
print("=================")
print("Grid dimensions: 35 x 35")
print("Total cells:", sum(len(row) for row in board))

groups = {}

for y, row in enumerate(board):
    for x, colour in enumerate(row):
        groups.setdefault(colour, []).append(rgb[y][x])

print("\nRGB COLOUR PROFILES")

for colour, pixels in sorted(groups.items()):
    channels = list(zip(*pixels))
    median = [
        sorted(channel)[len(channel)//2]
        for channel in channels
    ]

    print(
        colour,
        "| count:", len(pixels),
        "| median RGB:", tuple(median)
    )

print("\nVALIDATION PASSED")
