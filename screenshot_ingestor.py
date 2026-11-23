#!/usr/bin/env python
import argparse
import colorsys
import hashlib
import json
import statistics
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

BASELINE = Path("data/vision_level39.json")
OUTPUT = Path("data/board_observation_latest.json")


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
    return "pink"


def median_rgb(img, x, y):
    pixels = [
        img.getpixel((px, py))
        for py in range(y - 1, y + 2)
        for px in range(x - 1, x + 2)
    ]
    return tuple(
        int(statistics.median(pixel[channel] for pixel in pixels))
        for channel in range(3)
    )


def extract_board(image_path, calibration):
    image_path = Path(image_path)
    if not image_path.is_file():
        raise FileNotFoundError(image_path)

    with Image.open(image_path) as original:
        img = original.convert("RGB")
        width, height = img.size

        cols, rows = calibration["grid_size"]
        left, top, right, bottom = calibration["bounds"]

        if (
            type(cols) is not int or type(rows) is not int
            or cols < 1 or rows < 1
        ):
            raise ValueError("Grid dimensions must be positive integers")

        if (
            any(type(value) not in (int, float) for value in
                (left, top, right, bottom))
            or left < 1 or top < 1
            or right <= left or bottom <= top
            or right > width - 1 or bottom > height - 1
        ):
            raise ValueError(
                "Board bounds must be ordered and inside the screenshot "
                "with room for the 3x3 sampling window"
            )

        cell_width = (right - left) / cols
        cell_height = (bottom - top) / rows

        board, raw_rgb = [], []
        counts = {}

        for row in range(rows):
            labels, rgb_row = [], []
            for col in range(cols):
                x = round(left + (col + 0.5) * cell_width)
                y = round(top + (row + 0.5) * cell_height)
                rgb = median_rgb(img, x, y)
                colour = classify_rgb(rgb)
                labels.append(colour)
                rgb_row.append(list(rgb))
                counts[colour] = counts.get(colour, 0) + 1
            board.append(labels)
            raw_rgb.append(rgb_row)

    return {
        "image_size": [width, height],
        "grid_size": [cols, rows],
        "bounds": [left, top, right, bottom],
        "board": board,
        "raw_rgb": raw_rgb,
        "counts": counts,
    }


def ingest(image_path, baseline_path=BASELINE, output_path=OUTPUT, capture_session_id=None, captured_at=None):
    image_path = Path(image_path).expanduser().resolve()
    baseline = json.loads(Path(baseline_path).read_text())

    extracted = extract_board(image_path, baseline)
    digest = hashlib.sha256(image_path.read_bytes()).hexdigest()

    stat = image_path.stat()
    file_time = datetime.fromtimestamp(
        stat.st_mtime, timezone.utc
    ).isoformat()

    from capture_provenance import (
        parse_aware_capture_timestamp,
        parse_exif_capture_time,
        validate_capture_session_id,
    )
    with Image.open(image_path) as img:
        exif_time = parse_exif_capture_time(img.getexif())
    exif_time = (
        parse_aware_capture_timestamp(captured_at)
        if captured_at is not None else exif_time
    )
    capture_session_id = validate_capture_session_id(capture_session_id)

    snapshot_id = "sha256:" + digest

    result = {
        **extracted,
        "source": str(image_path),
        "source_sha256": digest,
        "snapshot_id": snapshot_id,
        "board_snapshot_id": snapshot_id,
        "captured_at": exif_time,
        "file_modified_at": file_time,
        "timestamp_identified": bool(exif_time),
        "capture_session_id": capture_session_id,
        "same_board_state_confirmed": False,
        "gameplay_verified": False,
        "vision_classification_verified": False,
        "game_taps_enabled": False,
        "note": (
            "Screenshot-derived visual observation only. "
            "File modification time is not proof of capture time. "
            "Board completeness and colour classification require validation."
        ),
    }

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(output_path.suffix + ".tmp")
    temporary.write_text(json.dumps(result, indent=2))
    temporary.replace(output_path)

    print("SLIME AI — SCREENSHOT INGESTION")
    print("=" * 48)
    print("Image:", image_path.name)
    print("Image dimensions:", extracted["image_size"])
    print("Board dimensions:", extracted["grid_size"])
    print("Extracted cells:", sum(extracted["counts"].values()))
    print("Colour counts:", extracted["counts"])
    print("SHA256:", digest)
    print("EXIF capture time identified:", bool(exif_time))
    print("Snapshot ID:", snapshot_id)
    print("Saved:", output_path)
    print("Gameplay verified: False")
    print("Game taps enabled: False")


def main():
    parser = argparse.ArgumentParser(
        description="Extract a board observation from a Slime Loop screenshot"
    )
    parser.add_argument("screenshot", help="Path to a complete game screenshot")
    parser.add_argument("--baseline", default=str(BASELINE))
    parser.add_argument("--output", default=str(OUTPUT))
    parser.add_argument("--capture-session-id")
    parser.add_argument("--captured-at", help="Explicit ISO-8601 capture time with UTC offset")
    args = parser.parse_args()
    ingest(args.screenshot, args.baseline, args.output, args.capture_session_id, args.captured_at)


if __name__ == "__main__":
    main()
