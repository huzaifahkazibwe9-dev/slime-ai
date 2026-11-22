from PIL import Image
from collections import Counter
from pathlib import Path
import colorsys
import json
import statistics

IMAGE = Path("screenshots/level39.jpg")
PALETTE_FILE = Path("data/shooter_palette.json")
OUTPUT_FILE = Path("data/vision_level39.json")

LEFT, RIGHT = 201, 881
TOP, BOTTOM = 431, 1113

COLS = 35
ROWS = 35

BACKGROUND_CANDIDATES = set()

SYMBOLS = {
    "cyan": "C",
    "green": "G",
    "white": "W",
    "blue": "B",
    "pink": "P",
    "red": "R",
    "purple": "U",
    "yellow": "Y",
    "orange": "O",
    "dark": "D",
    "gray": "-"
}


def median_rgb(img, x, y):
    pixels = [
        img.getpixel((px, py))
        for py in range(y - 1, y + 2)
        for px in range(x - 1, x + 2)
    ]

    return tuple(
        int(statistics.median(
            pixel[channel] for pixel in pixels
        ))
        for channel in range(3)
    )


def classify_rgb(rgb):
    r, g, b = [v / 255 for v in rgb]
    hue, saturation, value = colorsys.rgb_to_hsv(r, g, b)
    degrees = hue * 360

    if value < 0.22:
        return "dark"

    if saturation < 0.18:
        return "white" if value > 0.72 else "gray"

    if degrees < 12 or degrees >= 345:
        return "red"
    elif degrees < 38:
        return "orange"
    elif degrees < 68:
        return "yellow"
    elif degrees < 165:
        return "green"
    elif degrees < 205:
        return "cyan"
    elif degrees < 260:
        return "blue"
    elif degrees < 300:
        return "purple"
    else:
        return "pink"


def analyse():
    if not IMAGE.exists():
        raise FileNotFoundError(IMAGE)

    img = Image.open(IMAGE).convert("RGB")
    width, height = img.size

    if width < RIGHT or height < BOTTOM:
        raise ValueError("Screenshot is smaller than calibration bounds")

    cell_width = (RIGHT - LEFT) / COLS
    cell_height = (BOTTOM - TOP) / ROWS

    board = []
    raw_rgb = []
    occupancy_mask = []
    counts = Counter()
    foreground_counts = Counter()

    for row in range(ROWS):
        labels = []
        raw_row = []
        mask_row = []

        for col in range(COLS):
            x = round(LEFT + (col + 0.5) * cell_width)
            y = round(TOP + (row + 0.5) * cell_height)

            rgb = median_rgb(img, x, y)
            colour = classify_rgb(rgb)

            labels.append(colour)
            raw_row.append(list(rgb))

            occupied_candidate = (
                colour not in BACKGROUND_CANDIDATES
            )

            mask_row.append(int(occupied_candidate))

            counts[colour] += 1

            if occupied_candidate:
                foreground_counts[colour] += 1

        board.append(labels)
        raw_rgb.append(raw_row)
        occupancy_mask.append(mask_row)

    palette = None

    if PALETTE_FILE.exists():
        with open(PALETTE_FILE) as f:
            palette = json.load(f)

    output = {
        "image_size": [width, height],
        "grid_size": [COLS, ROWS],
        "bounds": [LEFT, TOP, RIGHT, BOTTOM],
        "legend": SYMBOLS,
        "counts": dict(counts),
        "board": board,
        "raw_rgb": raw_rgb,
        "occupancy": {
            "mask": occupancy_mask,
            "background_candidates": sorted(
                BACKGROUND_CANDIDATES
            ),
            "foreground_counts": dict(foreground_counts),
            "foreground_total": sum(foreground_counts.values()),
            "verified": False,
            "initial_occupancy_user_confirmed": True,
            "colour_classification_verified": False
        },
        "shooter_palette": palette
    }

    OUTPUT_FILE.write_text(json.dumps(output, indent=2))

    print("SLIME AI ENHANCED VISION")
    print("=======================")
    print("Image:", img.size)
    print("Grid:", COLS, "x", ROWS)
    print("Total cells:", COLS * ROWS)

    print("\nFOREGROUND CANDIDATES")
    for colour, count in sorted(foreground_counts.items()):
        print(f"{colour:10}: {count}")

    print("\nForeground total:", sum(foreground_counts.values()))
    print("Background candidates:", sorted(BACKGROUND_CANDIDATES))
    print("Palette loaded:", palette is not None)
    print("Occupancy verified: False")
    print("\nSaved:", OUTPUT_FILE)


if __name__ == "__main__":
    analyse()
