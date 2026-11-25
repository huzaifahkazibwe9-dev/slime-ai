"""Prepare an unverified template for human-confirmed shooter identity.

This tool creates structure only. It never guesses shooter positions, marks
records verified, or authorizes planning.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path

from conveyor_identity_matcher import (
    validate_calibration_positions,
    validate_required_position_layout,
)

DATA = Path("data")
BOARD_FILE = DATA / "board_observation_latest.json"
CALIBRATION_FILE = DATA / "conveyor_calibration.json"
DETECTION_FILE = DATA / "shooter_detection.json"
OUTPUT_FILE = DATA / "shooter_identity_observations.json"


def read_json_snapshot(path):
    raw = Path(path).read_bytes()
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{path}: invalid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return value, hashlib.sha256(raw).hexdigest()


def _sha256(value):
    return isinstance(value, str) and re.fullmatch(
        r"[0-9a-f]{64}", value
    ) is not None


def build_template(board, calibration, detection, source_hashes):
    """Create a blank, non-authoritative identity observation template."""
    errors = []
    source_sha256 = board.get("source_sha256")
    snapshot_id = board.get("snapshot_id")
    if (
        not _sha256(source_sha256)
        or snapshot_id != "sha256:" + source_sha256
        or board.get("board_snapshot_id") != snapshot_id
    ):
        errors.append("Board source hash and snapshot ID are missing or inconsistent")
    if not isinstance(board.get("capture_session_id"), str) or not board.get(
        "capture_session_id"
    ):
        errors.append("Board capture_session_id is missing")
    if not isinstance(board.get("captured_at"), str) or not board.get(
        "captured_at"
    ):
        errors.append("Board captured_at timestamp is missing")
    if board.get("timestamp_identified") is not True:
        errors.append("Board timestamp is not explicitly identified")

    raw_positions = calibration.get("shooters")
    positions = {
        item.get("id"): item
        for item in raw_positions
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    } if isinstance(raw_positions, list) else {}
    errors.extend(validate_calibration_positions(raw_positions))
    errors.extend(validate_required_position_layout(positions))

    raw_shooters = detection.get("visible_shooters")
    shooter_ids = []
    if not isinstance(raw_shooters, list) or not raw_shooters:
        errors.append("Shooter detection has no visible shooter records")
    else:
        for index, item in enumerate(raw_shooters):
            shooter_id = item.get("id") if isinstance(item, dict) else None
            if not isinstance(shooter_id, str) or not shooter_id:
                errors.append(f"Visible shooter {index} has an invalid ID")
            else:
                shooter_ids.append(shooter_id)
    if len(shooter_ids) != len(set(shooter_ids)):
        errors.append("Visible shooter IDs are not unique")

    required_sources = (
        "board_observation_json",
        "conveyor_calibration_json",
        "shooter_detection_json",
    )
    if any(not _sha256(source_hashes.get(name)) for name in required_sources):
        errors.append("One or more source SHA-256 fingerprints are missing")
    if errors:
        raise ValueError("; ".join(sorted(set(errors))))

    current_frame_id = "current_frame"
    observations = [
        {
            "frame_id": current_frame_id,
            "position_id": "",
            "shooter_id": shooter_id,
            "verified": False,
        }
        for shooter_id in shooter_ids
    ]
    for index, position_id in enumerate(sorted(positions)):
        observations.append({
            "frame_id": f"history_frame_{index + 1}",
            "position_id": position_id,
            "shooter_id": "",
            "verified": False,
        })

    return {
        "board_snapshot_id": snapshot_id,
        "capture_session_id": board["capture_session_id"],
        "captured_at": board["captured_at"],
        "timestamp_identified": True,
        "verified_by_user": False,
        "current_frame_id": current_frame_id,
        "observations": observations,
        "template_only": True,
        "source_file_sha256": dict(source_hashes),
        "instructions": (
            "Template only. Assign each visible shooter to its current "
            "calibrated position, fill historical frame records using "
            "independently checked screenshots, then set verified_by_user "
            "and each record's verified flag to true only after human review. "
            "Never copy predicted mappings. This file does not verify colour, "
            "ammunition OCR, or gameplay."
        ),
        "gameplay_verified": False,
        "game_taps_enabled": False,
        "actions_performed": False,
    }


def prepare_template(board_path=BOARD_FILE, calibration_path=CALIBRATION_FILE,
                     detection_path=DETECTION_FILE, output_path=OUTPUT_FILE):
    output_path = Path(output_path)
    if output_path.exists():
        return {
            "created": False,
            "preserved_existing": True,
            "output_path": str(output_path),
            "message": "Existing user identity observations were preserved.",
        }

    board, board_digest = read_json_snapshot(board_path)
    calibration, calibration_digest = read_json_snapshot(calibration_path)
    detection, detection_digest = read_json_snapshot(detection_path)
    source_hashes = {
        "board_observation_json": board_digest,
        "conveyor_calibration_json": calibration_digest,
        "shooter_detection_json": detection_digest,
    }
    template = build_template(board, calibration, detection, source_hashes)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(output_path.suffix + ".tmp")
    temporary.write_text(json.dumps(template, indent=2), encoding="utf-8")
    temporary.replace(output_path)
    return {
        "created": True,
        "preserved_existing": False,
        "output_path": str(output_path),
        "visible_shooters": len([
            item for item in template["observations"]
            if item["frame_id"] == template["current_frame_id"]
        ]),
        "historical_position_templates": len(template["observations"])
            - len([
                item for item in template["observations"]
                if item["frame_id"] == template["current_frame_id"]
            ]),
        "verified_by_user": False,
        "gameplay_verified": False,
        "game_taps_enabled": False,
    }


def main(board_path=BOARD_FILE, calibration_path=CALIBRATION_FILE,
         detection_path=DETECTION_FILE, output_path=OUTPUT_FILE):
    result = prepare_template(
        board_path, calibration_path, detection_path, output_path
    )
    print("SLIME AI — IDENTITY TEMPLATE PREPARATION")
    print("=" * 48)
    print("Created:", result["created"])
    print("Preserved existing:", result["preserved_existing"])
    for key in ("visible_shooters", "historical_position_templates"):
        if key in result:
            print(f"{key.replace('_', ' ').title()}:", result[key])
    print("User confirmation required: True")
    print("Gameplay verified: False")
    print("Game taps enabled: False")
    print("Report:", result["output_path"])
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Create a blank, unverified human identity observation template"
    )
    parser.add_argument("--board", default=str(BOARD_FILE))
    parser.add_argument("--calibration", default=str(CALIBRATION_FILE))
    parser.add_argument("--detection", default=str(DETECTION_FILE))
    parser.add_argument("--output", default=str(OUTPUT_FILE))
    args = parser.parse_args()
    main(args.board, args.calibration, args.detection, args.output)
