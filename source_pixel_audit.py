#!/usr/bin/env python3
"""Independently reproduce board RGB samples from the original screenshot."""
import argparse
import hashlib
import io
import json
import math
import re
import statistics
from collections import Counter
from pathlib import Path

from PIL import Image

from screenshot_ingestor import COLOUR_LABELS, classify_rgb, sample_centres_for_grid
from strict_json import strict_json_loads

SAMPLING_METHOD = "numpy_vectorized_3x3_median"
EXTRACTION_FINGERPRINT_FIELDS = (
    "image_size", "grid_size", "bounds", "sample_centres", "board",
    "raw_rgb", "counts", "sampling_method",
)


def canonical_observation_sha256(observation):
    """Fingerprint the complete parsed board observation using canonical JSON."""
    if not isinstance(observation, dict):
        return None
    try:
        encoded = json.dumps(
            observation, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    except (TypeError, ValueError):
        return None
    return hashlib.sha256(encoded).hexdigest()


AUDIT_STATUS_TRUE_FLAGS = (
    "source_image_hash_checked",
    "source_image_dimensions_checked",
)
AUDIT_STATUS_FALSE_FLAGS = (
    "label_truth_independently_verified",
    "calibration_alignment_verified",
    "gameplay_verified",
    "game_taps_enabled",
)


def validate_source_pixel_audit_status(report):
    """Require explicit audit checks and preserve all unverified status flags."""
    if not isinstance(report, dict):
        raise ValueError("Source-pixel audit report must be a JSON object")
    for flag in AUDIT_STATUS_TRUE_FLAGS:
        if report.get(flag) is not True:
            raise ValueError(f"Source-pixel audit {flag} must be True")
    for flag in AUDIT_STATUS_FALSE_FLAGS:
        if report.get(flag) is not False:
            raise ValueError(f"Source-pixel audit {flag} must remain False")
    return True


def _positive_int_pair(value, name):
    if (not isinstance(value, list) or len(value) != 2
            or any(type(item) is not int or item < 1 for item in value)):
        raise ValueError(f"{name} must contain two positive integers")
    return value


def _median_rgb(image, x, y):
    pixels = [
        image.getpixel((px, py))
        for py in range(y - 1, y + 2)
        for px in range(x - 1, x + 2)
    ]
    return [
        int(statistics.median(pixel[channel] for pixel in pixels))
        for channel in range(3)
    ]


def _extraction_fingerprint_matches(observation):
    """Check the ingestion payload digest using the repository's canonical encoding."""
    digest = observation.get("extraction_sha256")
    if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
        return False
    if any(field not in observation for field in EXTRACTION_FINGERPRINT_FIELDS):
        return False
    payload = {field: observation[field] for field in EXTRACTION_FINGERPRINT_FIELDS}
    try:
        encoded = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    except (TypeError, ValueError):
        return False
    return hashlib.sha256(encoded).hexdigest() == digest


def audit_source_pixels(observation, source_image_bytes):
    """Compare stored RGB samples with independent source-pixel medians."""
    if not isinstance(observation, dict):
        raise ValueError("Observation must be a JSON object")
    expected_hash = observation.get("source_sha256")
    if (not isinstance(expected_hash, str)
            or re.fullmatch(r"[0-9a-f]{64}", expected_hash) is None):
        raise ValueError("Observation requires a lowercase SHA-256 source_sha256")
    actual_hash = hashlib.sha256(source_image_bytes).hexdigest()
    if actual_hash != expected_hash:
        raise ValueError("Source screenshot SHA-256 does not match observation")

    try:
        image_context = Image.open(io.BytesIO(source_image_bytes))
        image_context.load()
    except Exception as exc:
        raise ValueError("Source screenshot is not a readable image") from exc

    with image_context as source:
        image = source.convert("RGB")
        image_size = _positive_int_pair(observation.get("image_size"), "image_size")
        if list(image.size) != image_size:
            raise ValueError("Source screenshot dimensions do not match observation")
        grid_size = _positive_int_pair(observation.get("grid_size"), "grid_size")
        columns, rows = grid_size
        if columns > 10_000 or rows > 10_000 or columns * rows > 1_000_000:
            raise ValueError("Grid dimensions exceed the safe audit limit")

        bounds = observation.get("bounds")
        if (not isinstance(bounds, list) or len(bounds) != 4
                or any(type(value) not in (int, float) for value in bounds)
                or any(type(value) is float and not math.isfinite(value) for value in bounds)):
            raise ValueError("bounds must contain four finite numeric coordinates")
        left, top, right, bottom = bounds
        if (left < 1 or top < 1 or right <= left or bottom <= top
                or right > image.width - 1 or bottom > image.height - 1):
            raise ValueError("bounds are outside screenshot sampling limits")
        if observation.get("sampling_method") != SAMPLING_METHOD:
            raise ValueError("Unsupported or missing sampling_method")

        expected_centres = sample_centres_for_grid(grid_size, bounds)
        if observation.get("sample_centres") != expected_centres:
            raise ValueError("sample_centres do not match grid_size and bounds")
        xs, ys = expected_centres["x"], expected_centres["y"]
        if (any(b - a < 3 for a, b in zip(xs, xs[1:]))
                or any(b - a < 3 for a, b in zip(ys, ys[1:]))):
            raise ValueError("3x3 sampling windows overlap")
        if any(x - 1 < 0 or x + 1 >= image.width for x in xs) or any(
            y - 1 < 0 or y + 1 >= image.height for y in ys
        ):
            raise ValueError("A 3x3 sampling window falls outside the screenshot")

        raw_rgb, board = observation.get("raw_rgb"), observation.get("board")
        if (not isinstance(raw_rgb, list) or len(raw_rgb) != rows
                or not isinstance(board, list) or len(board) != rows):
            raise ValueError("raw_rgb and board must match the declared row count")

        discrepancies, label_mismatches = [], []
        reproduced, counts = 0, Counter()
        for row in range(rows):
            if (not isinstance(raw_rgb[row], list) or len(raw_rgb[row]) != columns
                    or not isinstance(board[row], list) or len(board[row]) != columns):
                raise ValueError(f"Board/RGB row {row} has incorrect width")
            for column in range(columns):
                stored, label = raw_rgb[row][column], board[row][column]
                if (not isinstance(stored, list) or len(stored) != 3
                        or any(type(channel) is not int or not 0 <= channel <= 255
                               for channel in stored)):
                    raise ValueError(f"Malformed RGB sample at ({column},{row})")
                if not isinstance(label, str) or label not in COLOUR_LABELS:
                    raise ValueError(f"Invalid board label at ({column},{row})")
                expected = _median_rgb(image, xs[column], ys[row])
                if stored == expected:
                    reproduced += 1
                else:
                    discrepancies.append({
                        "row": row, "column": column,
                        "stored_rgb": stored, "source_median_rgb": expected,
                    })
                predicted_label = classify_rgb(expected)
                if label != predicted_label:
                    label_mismatches.append({
                        "row": row, "column": column,
                        "stored_label": label, "label_from_source_rgb": predicted_label,
                    })
                counts[label] += 1

        stored_counts = observation.get("counts")
        counts_well_formed = (
            isinstance(stored_counts, dict)
            and all(
                isinstance(key, str) and key in COLOUR_LABELS
                and type(value) is int and value > 0
                for key, value in stored_counts.items()
            )
        )
        counts_match = counts_well_formed and stored_counts == dict(counts)
        total = rows * columns
        return {
            "schema_version": 1,
            "source_sha256": actual_hash,
            "board_observation_sha256": canonical_observation_sha256(observation),
            "image_size": list(image.size),
            "grid_size": grid_size,
            "sample_count": total,
            "pixel_samples_reproduced": reproduced == total,
            "reproduced_sample_count": reproduced,
            "pixel_sample_mismatch_count": len(discrepancies),
            "pixel_sample_mismatches": discrepancies,
            "label_mismatch_count": len(label_mismatches),
            "label_mismatches": label_mismatches,
            "colour_counts_match": counts_match,
            "extraction_fingerprint_match": _extraction_fingerprint_matches(observation),
            "source_image_hash_checked": True,
            "source_image_dimensions_checked": True,
            "label_truth_independently_verified": False,
            "calibration_alignment_verified": False,
            "gameplay_verified": False,
            "game_taps_enabled": False,
            "interpretation": (
                "This audit independently reproduces stored RGB medians from the "
                "supplied screenshot and checks internal labels/counts. The optional "
                "extraction fingerprint detects accidental payload edits when the "
                "digest is not also recomputed. Neither check proves calibration "
                "alignment, game colour truth, or gameplay correctness."
            ),
        }


def main():
    parser = argparse.ArgumentParser(
        description="Independently audit board RGB samples against a source screenshot"
    )
    parser.add_argument("observation", help="Board observation JSON")
    parser.add_argument("--source-image", required=True, help="Original screenshot")
    parser.add_argument("--output", default="data/source_pixel_audit.json")
    args = parser.parse_args()
    observation = strict_json_loads(Path(args.observation).read_bytes())
    report = audit_source_pixels(observation, Path(args.source_image).read_bytes())
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(json.dumps(report, indent=2), encoding="utf-8")
    temporary.replace(output)

    print("SLIME AI — INDEPENDENT SOURCE-PIXEL AUDIT")
    print("=" * 48)
    print("Samples reproduced:", report["reproduced_sample_count"], "/", report["sample_count"])
    print("Pixel samples reproduced:", report["pixel_samples_reproduced"])
    print("Label mismatches:", report["label_mismatch_count"])
    print("Colour counts match:", report["colour_counts_match"])
    print("Extraction fingerprint matches:", report["extraction_fingerprint_match"])
    print("Calibration alignment verified: False")
    print("Gameplay verified: False")
    print("Game taps enabled: False")
    print("Report:", output)


if __name__ == "__main__":
    main()
