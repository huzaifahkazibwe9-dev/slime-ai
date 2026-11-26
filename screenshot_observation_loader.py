#!/usr/bin/env python3
"""Load the latest screenshot observation into a conservative GameState.

This adapter deliberately keeps visual observations separate from gameplay
verification. It never marks colours, removals, shooter accessibility, or
live actions as verified.
"""
import argparse
import hashlib
import io
import json
import math
import statistics
from collections import Counter
from pathlib import Path
from PIL import Image

from game_state import GameState
from shooter_loader import load_shooters
from screenshot_ingestor import (
    classify_rgb,
    validate_sample_window_geometry,
)
from strict_json import strict_json_loads
from capture_provenance import (
    parse_aware_capture_timestamp,
    validate_capture_session_id,
)

DEFAULT_OBSERVATION = Path("data/board_observation_latest.json")
DEFAULT_SHOOTERS = Path("data/shooter_detection.json")

def _is_finite_coordinate(value):
    """Accept exact integers or finite floats without overflowing on huge ints."""
    if type(value) is int:
        return True
    return type(value) is float and math.isfinite(value)



def _require_grid(data):
    if not isinstance(data, dict):
        raise ValueError("Observation must be a JSON object")

    grid = data.get("grid_size")
    image = data.get("image_size")
    bounds = data.get("bounds")
    board = data.get("board")
    rgb = data.get("raw_rgb")

    if (not isinstance(grid, list) or len(grid) != 2
            or any(type(v) is not int or v < 1 for v in grid)):
        raise ValueError("Invalid grid_size; expected positive [columns, rows]")
    if (not isinstance(image, list) or len(image) != 2
            or any(type(v) is not int or v < 1 for v in image)):
        raise ValueError("Invalid image_size")
    if (not isinstance(bounds, list) or len(bounds) != 4
            or any(not _is_finite_coordinate(v) for v in bounds)):
        raise ValueError("Invalid board bounds")

    width, height = grid
    image_width, image_height = image
    left, top, right, bottom = bounds
    if (left < 1 or top < 1 or right <= left or bottom <= top
            or right > image_width - 1 or bottom > image_height - 1):
        raise ValueError("Board bounds are outside the screenshot")
    # Enforce the ingestor's 3x3 sample-window geometry even when the
    # optional sample_centres metadata field is absent.
    expected_centres = validate_sample_window_geometry(
        grid, bounds, image
    )
    if (
        "sample_centres" in data
        and data.get("sample_centres") != expected_centres
    ):
        raise ValueError("Sample centres do not match calibrated board geometry")

    if not isinstance(board, list) or len(board) != height:
        raise ValueError("Board row count does not match grid_size")
    if not isinstance(rgb, list) or len(rgb) != height:
        raise ValueError("RGB row count does not match grid_size")

    counts = Counter()
    for y in range(height):
        if not isinstance(board[y], list) or len(board[y]) != width:
            raise ValueError(f"Board row {y} has incorrect width")
        if not isinstance(rgb[y], list) or len(rgb[y]) != width:
            raise ValueError(f"RGB row {y} has incorrect width")
        for x in range(width):
            label = board[y][x]
            sample = rgb[y][x]
            if not isinstance(label, str) or not label:
                raise ValueError(f"Invalid colour label at ({x},{y})")
            if (not isinstance(sample, list) or len(sample) != 3
                    or any(type(v) is not int or v < 0 or v > 255
                           for v in sample)):
                raise ValueError(f"Invalid RGB sample at ({x},{y})")
            if classify_rgb(sample) != label:
                raise ValueError(
                    f"RGB/classification mismatch at ({x},{y}): "
                    f"saved={label}, recalculated={classify_rgb(sample)}"
                )
            counts[label] += 1

    if data.get("counts") != dict(counts):
        raise ValueError("Saved colour counts do not match board labels")

    digest = data.get("source_sha256")
    snapshot_id = data.get("snapshot_id")
    board_snapshot_id = data.get("board_snapshot_id")
    if (not isinstance(digest, str) or len(digest) != 64
            or any(c not in "0123456789abcdef" for c in digest.lower())
            or snapshot_id != "sha256:" + digest
            or board_snapshot_id != snapshot_id):
        raise ValueError(
            "Invalid or inconsistent screenshot/board snapshot identity"
        )

    if data.get("gameplay_verified") is not False:
        raise ValueError("Screenshot observation must remain gameplay-unverified")
    if data.get("vision_classification_verified") is not False:
        raise ValueError("Screenshot colours must remain unverified")
    if data.get("game_taps_enabled") is not False:
        raise ValueError("Live game actions must remain disabled")

    return width, height, board, counts



def verify_source_samples(observation, source_image_bytes):
    """Independently recompute every saved 3x3 median from original image bytes."""
    if not isinstance(observation, dict):
        raise ValueError("Observation must be a JSON object")
    expected_digest = observation.get("source_sha256")
    actual_digest = hashlib.sha256(source_image_bytes).hexdigest()
    if expected_digest != actual_digest:
        raise ValueError("Source screenshot SHA-256 does not match observation")

    try:
        with Image.open(io.BytesIO(source_image_bytes)) as original:
            image = original.convert("RGB")
            image_size = list(image.size)
            pixels = image.load()
    except Exception as exc:
        raise ValueError("Source screenshot cannot be decoded") from exc

    if observation.get("image_size") != image_size:
        raise ValueError("Source screenshot dimensions do not match observation")

    grid = observation.get("grid_size")
    bounds = observation.get("bounds")
    if (not isinstance(grid, list) or len(grid) != 2
            or any(type(value) is not int or value < 1 for value in grid)
            or not isinstance(bounds, list) or len(bounds) != 4
            or any(not _is_finite_coordinate(value) for value in bounds)):
        raise ValueError("Invalid grid geometry for source sample verification")
    expected_centres = validate_sample_window_geometry(
        grid, bounds, image_size
    )
    if observation.get("sample_centres") != expected_centres:
        raise ValueError("Sample centres do not match calibrated board geometry")

    raw_rgb = observation.get("raw_rgb")
    cols, rows = grid
    if (not isinstance(raw_rgb, list) or len(raw_rgb) != rows
            or any(not isinstance(row, list) or len(row) != cols for row in raw_rgb)):
        raise ValueError("Raw RGB sample grid does not match observation dimensions")

    checked = 0
    for row, y in enumerate(expected_centres["y"]):
        for col, x in enumerate(expected_centres["x"]):
            recomputed = [
                int(statistics.median(
                    pixels[px, py][channel]
                    for py in range(y - 1, y + 2)
                    for px in range(x - 1, x + 2)
                ))
                for channel in range(3)
            ]
            if raw_rgb[row][col] != recomputed:
                raise ValueError(
                    f"Source RGB sample mismatch at column {col}, row {row}"
                )
            checked += 1

    return {
        "source_image_sha256_checked": True,
        "source_image_dimensions_checked": True,
        "source_rgb_samples_recomputed": checked,
        "source_rgb_samples_match": True,
    }


def _require_unverified_capture_status(data):
    """Require the state loader to preserve an explicitly unconfirmed board."""
    if not isinstance(data, dict):
        raise ValueError("Observation must be a JSON object")
    if data.get("same_board_state_confirmed") is not False:
        raise ValueError(
            "Screenshot observation must keep same_board_state_confirmed False"
        )


def load_observed_level(
    observation_path=DEFAULT_OBSERVATION,
    shooter_path=DEFAULT_SHOOTERS,
    level=39,
    observation_data=None,
    shooter_data=None,
):
    observation_path = Path(observation_path)
    shooter_path = Path(shooter_path)
    # Use the exact parsed objects validated by orchestration when supplied.
    # Path-based reads remain available for standalone diagnostic use.
    data = (
        observation_data
        if observation_data is not None
        else strict_json_loads(observation_path.read_bytes())
    )
    _require_unverified_capture_status(data)
    width, height, board, counts = _require_grid(data)

    if shooter_data is None:
        shooter_data = strict_json_loads(shooter_path.read_bytes())
    if not isinstance(shooter_data, dict):
        raise ValueError("Shooter detection must be a JSON object")
    shooter_provenance = shooter_data.get("capture_provenance", {})
    board_session = data.get("capture_session_id")
    board_timestamp = data.get("captured_at")
    try:
        normalized_board_session = validate_capture_session_id(board_session)
        normalized_board_timestamp = parse_aware_capture_timestamp(
            board_timestamp
        )
    except ValueError:
        normalized_board_session = None
        normalized_board_timestamp = None

    try:
        normalized_shooter_session = validate_capture_session_id(
            shooter_provenance.get("capture_session_id")
            if isinstance(shooter_provenance, dict) else None
        )
        normalized_shooter_timestamp = parse_aware_capture_timestamp(
            shooter_provenance.get("captured_at")
            if isinstance(shooter_provenance, dict) else None
        )
    except ValueError:
        normalized_shooter_session = None
        normalized_shooter_timestamp = None

    board_capture_metadata_valid = bool(
        normalized_board_session and normalized_board_timestamp
    )
    shooter_capture_metadata_valid = bool(
        normalized_shooter_session and normalized_shooter_timestamp
    )
    board_capture_matches = bool(
        isinstance(shooter_provenance, dict)
        and shooter_provenance.get("verified") is True
        and shooter_provenance.get("source_sha256") == data.get("source_sha256")
        and board_capture_metadata_valid
        and shooter_capture_metadata_valid
        and normalized_shooter_session == normalized_board_session
        and normalized_shooter_timestamp == normalized_board_timestamp
    )
    shooters = load_shooters(shooter_path, data=shooter_data)
    state = GameState(
        board=[row[:] for row in board],
        shooters=shooters,
        level=level,
    )
    # Preserve the legacy diagnostic interface without inventing mappings.
    state.colour_mappings = {}
    state.colour_mappings_verified = False
    state.snapshot_id = data["snapshot_id"]
    state.calibration_sha256 = data.get("calibration_sha256")
    state.capture_session_id = data.get("capture_session_id")
    state.timestamp_identified = data.get("timestamp_identified") is True
    state.shooter_capture_provenance_verified = board_capture_matches
    errors = state.validate()
    if errors:
        raise ValueError("Invalid integrated game state: " + "; ".join(errors))

    shooter_quality_counts = {}
    for shooter in shooters.values():
        quality_status = shooter.observation_quality.get(
            "sample_quality_status", "NOT_RECORDED"
        )
        shooter_quality_counts[quality_status] = (
            shooter_quality_counts.get(quality_status, 0) + 1
        )
    ammunition_ocr_status_counts = {}
    for shooter in shooters.values():
        ocr_status = shooter.observation_quality.get(
            "ammunition_ocr_status", "NOT_REPORTED"
        )
        ammunition_ocr_status_counts[ocr_status] = (
            ammunition_ocr_status_counts.get(ocr_status, 0) + 1
        )
    shooter_observation_quality = {
        "colour_independently_verified": all(
            shooter.observation_quality.get(
                "colour_independently_verified"
            ) is True for shooter in shooters.values()
        ) and bool(shooters),
        "ammunition_independently_verified": all(
            shooter.observation_quality.get(
                "ammunition_independently_verified"
            ) is True for shooter in shooters.values()
        ) and bool(shooters),
        "slot_mapping_independently_verified": all(
            shooter.observation_quality.get(
                "slot_mapping_independently_verified"
            ) is True for shooter in shooters.values()
        ) and bool(shooters),
        "shooters_loaded": len(shooters),
        "sample_quality_counts": shooter_quality_counts,
        "ammunition_ocr_status_counts": ammunition_ocr_status_counts,
        "interpretation": (
            "Detector outputs are observations for simulation only; "
            "colour, ammunition and slot mapping are not independently verified."
        ),
    }
    audit = {
        "source": "screenshot_observation",
        "shooter_observation_quality": shooter_observation_quality,
        "snapshot_id": data["snapshot_id"],
        "image_size": data["image_size"],
        "grid_size": [width, height],
        "board_cells": width * height,
        "colour_counts": dict(sorted(counts.items())),
        "classification_consistent_with_extractor": True,
        "colour_truth_verified": False,
        "shooter_count": len(shooters),
        "shooter_panel_positions_only": True,
        "board_capture_metadata_valid": board_capture_metadata_valid,
        "shooter_capture_metadata_valid": shooter_capture_metadata_valid,
        "shooter_capture_provenance_verified": board_capture_matches,
        "shooter_capture_source_matches_board": (
            shooter_provenance.get("source_sha256") == data.get("source_sha256")
            if isinstance(shooter_provenance, dict) else False
        ),
        "shooter_positions_gameplay_verified": False,
        "initial_occupancy_confirmed": False,
        "vision_occupancy_verified": False,
        "colour_classification_verified": False,
        "vision_classification_verified": False,
        "colour_mapping_verified": False,
        "board_transition_verified": False,
        "gameplay_verified": False,
        "game_taps_enabled": False,
    }
    return state, audit


def main():
    parser = argparse.ArgumentParser(
        description="Integrate the latest screenshot observation with detected shooters"
    )
    parser.add_argument("--observation", default=str(DEFAULT_OBSERVATION))
    parser.add_argument("--shooters", default=str(DEFAULT_SHOOTERS))
    parser.add_argument("--level", type=int, default=39)
    parser.add_argument("--source-image", help="Original screenshot for independent RGB sample verification")
    args = parser.parse_args()

    state, audit = load_observed_level(
        args.observation, args.shooters, args.level
    )
    print("SLIME AI — SCREENSHOT-TO-GAME-STATE INTEGRATION")
    print("=" * 54)
    print("Level:", state.level)
    print("Board:", state.width, "x", state.height)
    print("Observed cells:", state.remaining_pixels)
    print("Shooters:", len(state.shooters))
    print("Snapshot:", audit["snapshot_id"])
    print("State validation:", state.validate())
    if args.source_image:
        source_bytes = Path(args.source_image).read_bytes()
        verification = verify_source_samples(
            strict_json_loads(Path(args.observation).read_bytes()), source_bytes
        )
        print("\\nSOURCE IMAGE SAMPLE VERIFICATION")
        for key, value in verification.items():
            print(f"{key}: {value}")
    print("\nEVIDENCE STATUS")
    for key, value in audit.items():
        print(f"{key}: {value}")
    print("\nINTEGRATION PASSED")
    print("This is a candidate state, not a gameplay-verified state.")
    print("Game taps enabled: False")


if __name__ == "__main__":
    main()
