#!/usr/bin/env python3
"""Prepare a human-review template for shooter slot, colour and ammo observations.

The template keeps detector outputs separate from human labels. It cannot be
scored until every slot is marked confirmed or ambiguous and labelled_by_user
is explicitly changed to true.
"""
import argparse
from datetime import datetime
from io import BytesIO
import hashlib
import json
from pathlib import Path

from PIL import Image

SCHEMA_VERSION = 1
DETECTOR_COLOURS = (
    "black", "white", "gray", "red", "brown", "orange",
    "yellow", "green", "cyan", "blue", "purple", "magenta",
)
DETECTOR_STATUS_TO_VISIBILITY = {
    "readable_candidate": "visible",
    "unrevealed_candidate": "unrevealed",
    "partially_occluded_candidate": "partially_occluded",
}


def _valid_sha256(value):
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _positive_dimensions(value, name):
    if (not isinstance(value, list) or len(value) != 2
            or any(type(item) is not int or item < 1 for item in value)):
        raise ValueError(f"{name} must contain two positive integers")
    return value[:]


def _capture_metadata(detection):
    provenance = detection.get("capture_provenance")
    if not isinstance(provenance, dict) or provenance.get("verified") is not True:
        raise ValueError("Shooter capture provenance must be explicitly verified")
    source_hash = provenance.get("source_sha256")
    config_hash = provenance.get("capture_config_sha256")
    if not _valid_sha256(source_hash):
        raise ValueError("Capture provenance has no valid source screenshot SHA-256")
    if not _valid_sha256(config_hash):
        raise ValueError("Capture provenance has no valid capture-config SHA-256")
    session_id = provenance.get("capture_session_id")
    if not isinstance(session_id, str) or not session_id.strip():
        raise ValueError("Capture provenance has no capture_session_id")
    captured_at = provenance.get("captured_at")
    if not isinstance(captured_at, str) or not captured_at.strip():
        raise ValueError("Capture provenance has no captured_at timestamp")
    try:
        parsed = datetime.fromisoformat(captured_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Capture provenance captured_at is invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Capture provenance captured_at must include a UTC offset")
    bounds = provenance.get("panel_bounds")
    if (not isinstance(bounds, list) or len(bounds) != 4
            or any(type(item) is not int for item in bounds)
            or bounds[0] < 0 or bounds[1] < 0
            or bounds[2] <= bounds[0] or bounds[3] <= bounds[1]):
        raise ValueError("Capture provenance panel_bounds are invalid")
    return {
        "source_sha256": source_hash,
        "capture_config_sha256": config_hash,
        "capture_session_id": session_id,
        "captured_at": captured_at,
        "panel_bounds": bounds[:],
    }


def _validate_detector_layout(detection, panel_size):
    layout = detection.get("panel_layout")
    if not isinstance(layout, dict):
        raise ValueError("panel_layout must be an object")
    rows = layout.get("rows")
    columns = layout.get("columns")
    slot_count = layout.get("slot_count")
    if (type(rows) is not int or type(columns) is not int
            or rows < 1 or columns < 1
            or rows > 16 or columns > 16 or rows * columns > 256):
        raise ValueError("panel_layout rows and columns must be positive and bounded")
    if type(slot_count) is not int or slot_count != rows * columns:
        raise ValueError("panel_layout slot_count must equal rows multiplied by columns")

    slots = detection.get("panel_slots")
    observations = detection.get("panel_slot_observations")
    if not isinstance(slots, list) or not isinstance(observations, list):
        raise ValueError("panel_slots and panel_slot_observations must be lists")
    if len(slots) != slot_count or len(observations) != slot_count:
        raise ValueError("Panel slot lists must contain exactly panel_layout.slot_count entries")

    slot_by_id = {}
    positions = set()
    for index, slot in enumerate(slots):
        if not isinstance(slot, dict):
            raise ValueError(f"panel_slots[{index}] must be an object")
        slot_id = slot.get("id")
        row, column = slot.get("row"), slot.get("column")
        if not isinstance(slot_id, str) or not slot_id.strip():
            raise ValueError(f"panel_slots[{index}] has an invalid id")
        if (type(row) is not int or type(column) is not int
                or not 1 <= row <= rows or not 1 <= column <= columns):
            raise ValueError(f"panel_slots[{index}] has invalid one-based row/column")
        position = (row, column)
        if slot_id in slot_by_id:
            raise ValueError(f"Duplicate panel slot id: {slot_id}")
        if position in positions:
            raise ValueError(f"Duplicate panel slot position: row={row}, column={column}")
        positions.add(position)
        slot_by_id[slot_id] = slot

    expected_positions = {
        (row, column)
        for row in range(1, rows + 1)
        for column in range(1, columns + 1)
    }
    if positions != expected_positions:
        raise ValueError("panel_slots do not cover every calibrated row/column position")

    samples = []
    seen_observation_ids = set()
    observed_positions = set()
    for index, observation in enumerate(observations):
        if not isinstance(observation, dict):
            raise ValueError(f"panel_slot_observations[{index}] must be an object")
        slot_id = observation.get("id")
        row, column = observation.get("row"), observation.get("column")
        if not isinstance(slot_id, str) or slot_id not in slot_by_id:
            raise ValueError(f"panel_slot_observations[{index}] has an unknown slot id")
        if slot_id in seen_observation_ids:
            raise ValueError(f"Duplicate panel observation id: {slot_id}")
        seen_observation_ids.add(slot_id)
        if (type(row) is not int or type(column) is not int
                or (row, column) != (
                    slot_by_id[slot_id].get("row"),
                    slot_by_id[slot_id].get("column"),
                )):
            raise ValueError(f"Observation {slot_id} row/column does not match panel_slots")
        observed_positions.add((row, column))

        status = observation.get("status")
        if status not in DETECTOR_STATUS_TO_VISIBILITY:
            raise ValueError(f"Observation {slot_id} has an unsupported detector status")
        colour_record = observation.get("color_observation")
        if (not isinstance(colour_record, dict)
                or colour_record.get("name") not in DETECTOR_COLOURS):
            raise ValueError(f"Observation {slot_id} has an invalid detected colour")
        ammo = observation.get("ammunition_observation")
        if ammo is not None and (type(ammo) is not int or ammo < 0):
            raise ValueError(f"Observation {slot_id} has invalid detected ammunition")

        center = observation.get("screen_center")
        sample = observation.get("screen_sample")
        box = observation.get("screen_box")
        if (not isinstance(center, list) or len(center) != 2
                or any(type(value) is not int for value in center)):
            raise ValueError(f"Observation {slot_id} screen_center is invalid")
        if (not isinstance(sample, list) or len(sample) != 2
                or any(type(value) is not int for value in sample)):
            raise ValueError(f"Observation {slot_id} screen_sample is invalid")
        if (not isinstance(box, list) or len(box) != 4
                or any(type(value) is not int for value in box)
                or not (0 <= box[0] < box[2] <= panel_size[0]
                        and 0 <= box[1] < box[3] <= panel_size[1])):
            raise ValueError(f"Observation {slot_id} screen_box is outside panel dimensions")
        if not (0 <= center[0] < panel_size[0] and 0 <= center[1] < panel_size[1]
                and 0 <= sample[0] < panel_size[0] and 0 <= sample[1] < panel_size[1]):
            raise ValueError(f"Observation {slot_id} screen coordinates are outside panel dimensions")

        quality = observation.get("sample_quality")
        quality_status = None
        if quality is not None:
            if not isinstance(quality, dict):
                raise ValueError(f"Observation {slot_id} sample_quality must be an object")
            quality_status = quality.get("status")
            if quality_status not in {"DISTINCT_SAMPLE", "LOW_CONFIDENCE_SAMPLE"}:
                raise ValueError(f"Observation {slot_id} sample_quality status is invalid")

        samples.append({
            "detector": {
                "id": slot_id,
                "row": row,
                "column": column,
                "status": status,
                "visibility": DETECTOR_STATUS_TO_VISIBILITY[status],
                "colour": colour_record["name"],
                "ammunition": ammo,
                "sample_quality_status": quality_status,
                "screen_center": center[:],
                "screen_box": box[:],
                "screen_sample": sample[:],
            },
            "review_status": "not_reviewed",
            "human": {
                "visibility": "",
                "row": None,
                "column": None,
                "colour": "",
                "ammunition_readable": None,
                "ammunition": None,
            },
        })

    if seen_observation_ids != set(slot_by_id) or observed_positions != expected_positions:
        raise ValueError("Detector observations do not cover the calibrated panel slots")
    return {
        "rows": rows,
        "columns": columns,
        "slot_count": slot_count,
    }, samples


def build_template(detection, detection_bytes, screenshot_bytes):
    """Build a blank review dataset tied to exact detector and screenshot bytes."""
    if not isinstance(detection, dict):
        raise ValueError("Shooter detection must be a JSON object")
    if not isinstance(detection_bytes, bytes) or not detection_bytes:
        raise ValueError("Exact shooter detection JSON bytes are required")
    if not isinstance(screenshot_bytes, bytes) or not screenshot_bytes:
        raise ValueError("Original screenshot bytes are required")
    try:
        parsed_bytes = json.loads(detection_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Shooter detection bytes are not valid JSON") from exc
    if not isinstance(parsed_bytes, dict) or parsed_bytes != detection:
        raise ValueError("Detection object does not match the exact supplied JSON bytes")

    capture = _capture_metadata(detection)
    screenshot_hash = hashlib.sha256(screenshot_bytes).hexdigest()
    if screenshot_hash != capture["source_sha256"]:
        raise ValueError("Original screenshot SHA-256 does not match shooter capture provenance")
    try:
        with Image.open(BytesIO(screenshot_bytes)) as image:
            screenshot_size = list(image.size)
    except Exception as exc:
        raise ValueError("Original screenshot bytes are not a readable image") from exc

    panel_size = _positive_dimensions(
        detection.get("image_dimensions"), "image_dimensions"
    )
    left, top, right, bottom = capture["panel_bounds"]
    screenshot_width, screenshot_height = screenshot_size
    if right > screenshot_width or bottom > screenshot_height:
        raise ValueError("Capture provenance panel_bounds are outside the source screenshot")
    crop_ratio = (right - left) / (bottom - top)
    panel_ratio = panel_size[0] / panel_size[1]
    if abs(crop_ratio - panel_ratio) / panel_ratio > 0.02:
        raise ValueError("Capture panel bounds aspect ratio does not match detector panel dimensions")
    layout, samples = _validate_detector_layout(detection, panel_size)
    observation_quality = detection.get("observation_quality", {})
    if not isinstance(observation_quality, dict):
        raise ValueError("observation_quality must be an object")

    return {
        "schema_version": SCHEMA_VERSION,
        "labelled_by_user": False,
        "source_detection_sha256": hashlib.sha256(detection_bytes).hexdigest(),
        "source_screenshot_sha256": screenshot_hash,
        "source_screenshot_size": screenshot_size,
        "panel_image_size": panel_size,
        "capture_provenance": capture,
        "panel_layout": layout,
        "detector_observation_quality": {
            "colour_independently_verified": observation_quality.get(
                "colour_independently_verified", False
            ),
            "ammunition_independently_verified": observation_quality.get(
                "ammunition_independently_verified", False
            ),
            "slot_mapping_independently_verified": observation_quality.get(
                "slot_mapping_independently_verified", False
            ),
        },
        "samples": samples,
        "labelling_instructions": (
            "Inspect the original screenshot and review every fixed panel coordinate. "
            "Mark each sample confirmed or ambiguous. For confirmed samples, record "
            "what is actually visible at the sampled location, its actual one-based "
            "row and column (or null when it does not land on a slot), and its colour "
            "and ammunition only when visible. Do not copy detector outputs into the "
            "human fields. Set labelled_by_user to true only after completing the "
            "manual review of every sample."
        ),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Prepare a human-review template for shooter panel observations"
    )
    parser.add_argument("detection", help="shooter_detection.json from the capture pipeline")
    parser.add_argument("source_screenshot", help="Exact original screenshot used for detection")
    parser.add_argument("--output", default="data/shooter_labels_template.json")
    args = parser.parse_args()

    detection_bytes = Path(args.detection).read_bytes()
    try:
        detection = json.loads(detection_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Shooter detection file is not valid UTF-8 JSON") from exc
    screenshot_bytes = Path(args.source_screenshot).read_bytes()
    template = build_template(detection, detection_bytes, screenshot_bytes)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(json.dumps(template, indent=2), encoding="utf-8")
    temporary.replace(output)

    print("SLIME AI — HUMAN SHOOTER REVIEW TEMPLATE")
    print("=" * 46)
    print("Panel slots prepared:", len(template["samples"]))
    print("Source screenshot SHA256:", template["source_screenshot_sha256"])
    print("Source detector SHA256:", template["source_detection_sha256"])
    print("User labels supplied: False")
    print("Evaluation-ready: False")
    print("Template:", output)


if __name__ == "__main__":
    main()
