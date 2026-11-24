#!/usr/bin/env python
import argparse
import colorsys
import hashlib
import json
import math
import statistics
import time

import numpy as np
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

BASELINE = Path("data/vision_level39.json")
OUTPUT = Path("data/board_observation_latest.json")

COLOUR_LABELS = (
    "dark", "white", "gray", "red", "orange", "yellow",
    "green", "cyan", "blue", "purple", "pink",
)


def _is_finite_number(value):
    """Accept exact ints and finite floats, excluding bool and huge-int overflow."""
    if type(value) is int:
        return True
    return type(value) is float and math.isfinite(value)


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
    started = time.perf_counter()
    image_path = Path(image_path)
    if not image_path.is_file():
        raise FileNotFoundError(image_path)

    with Image.open(image_path) as original:
        img = original.convert("RGB")
        width, height = img.size

        if not isinstance(calibration, dict):
            raise ValueError("Calibration must be a JSON object")
        grid_size = calibration.get("grid_size")
        bounds = calibration.get("bounds")
        if not isinstance(grid_size, list) or len(grid_size) != 2:
            raise ValueError("Calibration grid_size must be [columns, rows]")
        if not isinstance(bounds, list) or len(bounds) != 4:
            raise ValueError("Calibration bounds must contain four coordinates")
        cols, rows = grid_size
        left, top, right, bottom = bounds

        if (
            type(cols) is not int or type(rows) is not int
            or cols < 1 or rows < 1
        ):
            raise ValueError("Grid dimensions must be positive integers")

        if (
            any(not _is_finite_number(value)
                for value in (left, top, right, bottom))
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
        pixels = np.asarray(img, dtype=np.uint8)

        board, raw_rgb = [], []
        counts = {}

        for row in range(rows):
            labels, rgb_row = [], []
            for col in range(cols):
                x = round(left + (col + 0.5) * cell_width)
                y = round(top + (row + 0.5) * cell_height)
                # NumPy computes the exact 3x3 per-channel median in one
                # vectorised operation, avoiding nine PIL getpixel calls.
                patch = pixels[y - 1:y + 2, x - 1:x + 2]
                rgb = tuple(int(v) for v in np.median(patch, axis=(0, 1)))
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
        "processing_seconds": round(time.perf_counter() - started, 6),
        "sampling_method": "numpy_vectorized_3x3_median",
    }


def _extraction_payload_sha256(extracted):
    """Fingerprint cached extraction fields to detect accidental payload edits."""
    payload = {
        key: extracted[key]
        for key in (
            "image_size", "grid_size", "bounds", "board", "raw_rgb",
            "counts", "sampling_method"
        )
    }
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _cached_board_is_valid(cached, digest, calibration_digest, image_size, calibration):
    """Accept cached pixels only for an exact source/configuration match."""
    if not isinstance(cached, dict):
        return False
    if cached.get("source_sha256") != digest:
        return False
    if cached.get("calibration_sha256") != calibration_digest:
        return False
    cached_image_size = cached.get("image_size")
    if (
        not isinstance(cached_image_size, list)
        or len(cached_image_size) != 2
        or any(type(value) is not int or value < 1
               for value in cached_image_size)
        or cached_image_size != list(image_size)
    ):
        return False

    grid_size = calibration.get("grid_size")
    bounds = calibration.get("bounds")
    if (not isinstance(grid_size, list) or len(grid_size) != 2
            or any(type(value) is not int or value < 1 for value in grid_size)
            or not isinstance(bounds, list) or len(bounds) != 4
            or any(not _is_finite_number(value) for value in bounds)):
        return False
    cached_grid_size = cached.get("grid_size")
    cached_bounds = cached.get("bounds")
    if (
        not isinstance(cached_grid_size, list)
        or len(cached_grid_size) != 2
        or any(type(value) is not int or value < 1
               for value in cached_grid_size)
        or cached_grid_size != grid_size
        or not isinstance(cached_bounds, list)
        or len(cached_bounds) != 4
        or any(not _is_finite_number(value) for value in cached_bounds)
        or cached_bounds != bounds
    ):
        return False
    left, top, right, bottom = bounds
    image_width, image_height = image_size
    if (left < 1 or top < 1 or right <= left or bottom <= top
            or right > image_width - 1 or bottom > image_height - 1):
        return False
    board = cached.get("board")
    raw_rgb = cached.get("raw_rgb")
    counts = cached.get("counts")
    if (not isinstance(counts, dict)
            or not isinstance(board, list) or len(board) != grid_size[1]
            or not isinstance(raw_rgb, list) or len(raw_rgb) != grid_size[1]
            or cached.get("sampling_method") != "numpy_vectorized_3x3_median"):
        return False
    if any(
        not isinstance(row, list) or len(row) != grid_size[0]
        or any(label not in COLOUR_LABELS for label in row)
        for row in board
    ):
        return False
    if any(
        not isinstance(row, list) or len(row) != grid_size[0]
        or any(
            not isinstance(rgb, list) or len(rgb) != 3
            or any(type(channel) is not int or not 0 <= channel <= 255
                   for channel in rgb)
            for rgb in row
        )
        for row in raw_rgb
    ):
        return False

    # The cached labels must be reproducible from the cached RGB samples.
    # This detects internally inconsistent cache records; it does not prove
    # that the shared classifier matches the game's true tile colours.
    for row_index, row in enumerate(board):
        for column_index, label in enumerate(row):
            if classify_rgb(raw_rgb[row_index][column_index]) != label:
                return False

    # Require exact integer counts: bool is an int subclass in Python and
    # would otherwise compare equal to 0 or 1 in a dictionary.
    if any(
        key not in COLOUR_LABELS or type(value) is not int or value < 1
        for key, value in counts.items()
    ):
        return False

    actual_counts = {}
    for row in board:
        for label in row:
            actual_counts[label] = actual_counts.get(label, 0) + 1
    if counts != actual_counts:
        return False

    # Detect accidental edits to cached extraction data. This is not an
    # authenticity signature; a writer can recompute it after editing.
    try:
        return cached.get("extraction_sha256") == _extraction_payload_sha256(cached)
    except (KeyError, TypeError, ValueError):
        return False


def ingest(image_path, baseline_path=BASELINE, output_path=OUTPUT, capture_session_id=None, captured_at=None):
    started = time.perf_counter()
    image_path = Path(image_path).expanduser().resolve()
    output_path = Path(output_path)
    baseline = json.loads(Path(baseline_path).read_text())
    if not isinstance(baseline, dict):
        raise ValueError("Calibration must be a JSON object")

    # Hash exact bytes, not a perceptual approximation. Calibration is
    # fingerprinted separately so any edit invalidates cached extraction.
    digest = hashlib.sha256(image_path.read_bytes()).hexdigest()
    calibration_bytes = json.dumps(
        baseline, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    calibration_digest = hashlib.sha256(calibration_bytes).hexdigest()

    with Image.open(image_path) as source_image:
        image_size = source_image.size

    cached = None
    try:
        cached = json.loads(output_path.read_text())
    except (OSError, json.JSONDecodeError):
        pass

    if _cached_board_is_valid(
        cached, digest, calibration_digest, image_size, baseline
    ):
        extracted = {
            key: cached[key]
            for key in (
                "image_size", "grid_size", "bounds", "board", "raw_rgb",
                "counts", "sampling_method"
            )
        }
        extracted["processing_seconds"] = 0.0
        cache_status = "EXACT_MATCH_REUSED"
    else:
        extracted = extract_board(image_path, baseline)
        cache_status = "FULL_ANALYSIS"

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

    extraction_sha256 = _extraction_payload_sha256(extracted)
    result = {
        **extracted,
        "extraction_sha256": extraction_sha256,
        "source": str(image_path),
        "source_sha256": digest,
        "calibration_sha256": calibration_digest,
        "analysis_cache_status": cache_status,
        "ingestion_seconds": round(time.perf_counter() - started, 6),
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
