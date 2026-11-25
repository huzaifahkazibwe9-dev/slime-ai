"""Build a provenance-bound, human-confirmed shooter identity audit.

This module validates explicit user-confirmed position-to-shooter records.
It does not infer identity from colour, OCR, or image similarity, and it
never claims gameplay verification or authorizes device actions.
"""
import argparse
import hashlib
import json
from strict_json import strict_json_loads
import re
from datetime import datetime
from pathlib import Path

from capture_provenance import validate_capture_session_id

DATA = Path("data")
BOARD_FILE = DATA / "board_observation_latest.json"
VISUAL_FILE = DATA / "conveyor_visual_observations.json"
IDENTITY_FILE = DATA / "shooter_identity_observations.json"
CALIBRATION_FILE = DATA / "conveyor_calibration.json"
DETECTION_FILE = DATA / "shooter_detection.json"
OUTPUT_FILE = DATA / "identity_audit_report.json"


def _sha256(value):
    return (
        isinstance(value, str)
        and re.fullmatch(r"[0-9a-f]{64}", value) is not None
    )


def _timestamp(value):
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed


def read_json_snapshot(path):
    """Parse one JSON object and hash the exact bytes used to parse it."""
    raw = Path(path).read_bytes()
    value = strict_json_loads(raw)
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return value, hashlib.sha256(raw).hexdigest()


def audit_identity(board, visual, identity_data, calibration, detection,
                   current_source_file_sha256=None):
    """Validate one user-confirmed identity frame against a current capture."""
    errors = []
    board = board if isinstance(board, dict) else {}
    visual = visual if isinstance(visual, dict) else {}
    identity_data = identity_data if isinstance(identity_data, dict) else {}
    calibration = calibration if isinstance(calibration, dict) else {}
    detection = detection if isinstance(detection, dict) else {}
    board_id = board.get("snapshot_id")
    board_source = board.get("source_sha256") if isinstance(board, dict) else None
    board_session = board.get("capture_session_id") if isinstance(board, dict) else None
    board_time_text = board.get("captured_at") if isinstance(board, dict) else None
    board_time = _timestamp(board_time_text)

    if not isinstance(board, dict):
        errors.append("Board observation must be a JSON object")
    else:
        if not _sha256(board_source):
            errors.append("Board source_sha256 is missing or malformed")
        if board_id != ("sha256:" + board_source if _sha256(board_source) else None):
            errors.append("Board snapshot_id does not match its source SHA-256")
        try:
            validate_capture_session_id(board_session)
        except ValueError:
            errors.append("Board capture_session_id is missing or malformed")
        if board_time is None:
            errors.append("Board capture timestamp must include a UTC offset")
        if board.get("timestamp_identified") is not True:
            errors.append("Board capture timestamp is not explicitly identified")

    if not isinstance(visual, dict):
        errors.append("Conveyor visual observations must be a JSON object")
        visual = {}
    if visual.get("board_snapshot_id") != board_id:
        errors.append("Conveyor observations do not match the current board snapshot")
    if visual.get("capture_session_id") != board_session:
        errors.append("Conveyor observations do not match the current capture session")
    visual_time = _timestamp(visual.get("captured_at"))
    if visual_time is None:
        errors.append("Conveyor observation timestamp must include a UTC offset")
    elif board_time is not None and abs(
        (visual_time - board_time).total_seconds()
    ) > 120:
        errors.append("Conveyor observation timestamp differs from the board capture by more than 120 seconds")
    if visual.get("timestamp_identified") is not True:
        errors.append("Conveyor observation timestamp is not explicitly identified")
    if visual.get("same_board_state_confirmed") is not True:
        errors.append("Conveyor observations lack explicit same-board confirmation")

    if not isinstance(calibration, dict):
        errors.append("Conveyor calibration must be a JSON object")
        calibration = {}
    raw_positions = calibration.get("shooters")
    positions = {}
    if not isinstance(raw_positions, list) or not raw_positions:
        errors.append("Calibration has no shooter positions")
    else:
        for index, item in enumerate(raw_positions):
            if not isinstance(item, dict):
                errors.append(f"Calibration position {index} is not an object")
                continue
            position_id = item.get("id")
            if not isinstance(position_id, str) or not position_id.strip():
                errors.append(f"Calibration position {index} has an invalid ID")
                continue
            if position_id in positions:
                errors.append(f"Duplicate calibrated position: {position_id}")
            positions[position_id] = item

    if not isinstance(detection, dict):
        errors.append("Shooter detection must be a JSON object")
        detection = {}
    raw_shooters = detection.get("visible_shooters")
    known_shooters = set()
    if not isinstance(raw_shooters, list) or not raw_shooters:
        errors.append("Shooter detection has no visible shooter records")
    else:
        for index, item in enumerate(raw_shooters):
            if not isinstance(item, dict):
                errors.append(f"Detected shooter {index} is not an object")
                continue
            shooter_id = item.get("id")
            if not isinstance(shooter_id, str) or not shooter_id.strip():
                errors.append(f"Detected shooter {index} has an invalid ID")
                continue
            if shooter_id in known_shooters:
                errors.append(f"Duplicate detected shooter ID: {shooter_id}")
            known_shooters.add(shooter_id)

    if not isinstance(identity_data, dict):
        errors.append("Identity observations must be a JSON object")
        identity_data = {}
    if identity_data.get("verified_by_user") is not True:
        errors.append("Identity observations are not explicitly user-confirmed")
    if identity_data.get("board_snapshot_id") != board_id:
        errors.append("Identity observations do not match the current board snapshot")
    if identity_data.get("capture_session_id") != board_session:
        errors.append("Identity observations do not match the current capture session")
    identity_time = _timestamp(identity_data.get("captured_at"))
    if identity_time is None:
        errors.append("Identity observation timestamp must include a UTC offset")
    elif board_time is not None and abs(
        (identity_time - board_time).total_seconds()
    ) > 120:
        errors.append("Identity observation timestamp differs from the board capture by more than 120 seconds")
    if identity_data.get("timestamp_identified") is not True:
        errors.append("Identity observation timestamp is not explicitly identified")

    if current_source_file_sha256 is not None:
        expected_template_sources = {
            "board_observation_json": current_source_file_sha256.get(
                "board_observation_json"
            ),
            "conveyor_visual_observations_json": current_source_file_sha256.get(
                "conveyor_visual_observations_json"
            ),
            "conveyor_calibration_json": current_source_file_sha256.get(
                "conveyor_calibration_json"
            ),
            "shooter_detection_json": current_source_file_sha256.get(
                "shooter_detection_json"
            ),
        }
        template_sources = identity_data.get("source_file_sha256")
        if (
            not isinstance(template_sources, dict)
            or template_sources != expected_template_sources
            or any(not _sha256(value) for value in expected_template_sources.values())
        ):
            errors.append(
                "Identity template source fingerprints do not match the current board, "
                "visual, calibration, and shooter files"
            )

    current_frame_id = identity_data.get("current_frame_id")
    if not isinstance(current_frame_id, str) or not current_frame_id.strip():
        errors.append("Identity observations must identify the current_frame_id")

    observations = identity_data.get("observations")
    if not isinstance(observations, list):
        observations = []
        errors.append("Identity observations must be a list")

    frame_ids = set()
    frame_positions = {}
    frame_shooters = {}
    seen_positions = set()
    position_to_shooters = {}
    for index, item in enumerate(observations):
        if not isinstance(item, dict):
            errors.append(f"Identity record {index} must be an object")
            continue
        frame_id = item.get("frame_id")
        position_id = item.get("position_id")
        shooter_id = item.get("shooter_id")
        if not isinstance(frame_id, str) or not frame_id.strip():
            errors.append(f"Identity record {index} has an invalid frame_id")
            continue
        frame_ids.add(frame_id)
        if not isinstance(position_id, str) or position_id not in positions:
            errors.append(f"Identity record {index} has an unknown calibrated position")
            continue
        if not isinstance(shooter_id, str) or shooter_id not in known_shooters:
            errors.append(f"Identity record {index} references an unknown shooter")
            continue
        positions_in_frame = frame_positions.setdefault(frame_id, set())
        shooters_in_frame = frame_shooters.setdefault(frame_id, set())
        if position_id in positions_in_frame:
            errors.append(
                f"Duplicate position in frame {frame_id}: {position_id}"
            )
        else:
            positions_in_frame.add(position_id)
        if shooter_id in shooters_in_frame:
            errors.append(
                f"Frame {frame_id}: duplicate shooter {shooter_id}"
            )
        else:
            shooters_in_frame.add(shooter_id)
        seen_positions.add(position_id)
        position_to_shooters.setdefault(position_id, set()).add(shooter_id)
        if item.get("verified") is not True:
            errors.append(f"Identity record {index} is not individually user-confirmed")

    expected_positions = set(positions)
    current_frame_positions = frame_positions.get(current_frame_id, set())
    current_frame_shooters = frame_shooters.get(current_frame_id, set())
    if current_frame_id not in frame_ids:
        errors.append("current_frame_id does not identify a recorded frame")
    if not current_frame_positions:
        errors.append("Current identity frame contains no calibrated positions")
    if current_frame_shooters != known_shooters:
        errors.append(
            "Current identity frame must map every currently detected shooter exactly once"
        )
    if len(current_frame_positions) != len(current_frame_shooters):
        errors.append(
            "Current identity frame must map distinct shooters to distinct positions"
        )
    current_position_by_shooter = {
        shooter_id: position_id
        for position_id, shooter_ids in position_to_shooters.items()
        if position_id in current_frame_positions
        for shooter_id in shooter_ids
        if any(
            isinstance(item, dict)
            and item.get("frame_id") == current_frame_id
            and item.get("position_id") == position_id
            and item.get("shooter_id") == shooter_id
            for item in observations
        )
    }
    if expected_positions - seen_positions:
        errors.append(
            "Identity observations are missing calibrated positions: "
            + ", ".join(sorted(expected_positions - seen_positions))
        )
    if not frame_ids:
        errors.append("Identity observations contain no capture frame IDs")
    if not observations:
        errors.append("Identity observations contain no records")

    visual_observations = visual.get("observations")
    visual_positions = {
        item.get("position_id")
        for item in visual_observations
        if isinstance(item, dict) and isinstance(item.get("position_id"), str)
    } if isinstance(visual_observations, list) else set()
    if visual_positions != expected_positions:
        errors.append("Conveyor visual positions do not exactly match calibrated positions")

    errors = sorted(set(errors))
    timestamps_known = (
        board_time is not None
        and board.get("timestamp_identified") is True
        and visual_time is not None
        and visual.get("timestamp_identified") is True
        and identity_time is not None
        and identity_data.get("timestamp_identified") is True
    )
    return {
        "identity_verified": not errors,
        "timestamps_known": timestamps_known,
        "positions_checked": len(current_position_by_shooter),
        "known_shooters": sorted(known_shooters),
        "position_to_shooters": {
            position: sorted(shooter_ids)
            for position, shooter_ids in sorted(position_to_shooters.items())
        },
        "shooter_positions": {
            shooter_id: sorted(
                position for position, shooter_ids in position_to_shooters.items()
                if shooter_id in shooter_ids
            )
            for shooter_id in sorted(known_shooters)
        },
        "identity_frame_ids": sorted(frame_ids),
        "current_frame_id": current_frame_id,
        "current_position_by_shooter": current_position_by_shooter,
        "board_snapshot_id": board_id,
        "capture_session_id": board_session,
        "captured_at": board_time.isoformat() if board_time else None,
        "timestamp_identified": board_time is not None
            and board.get("timestamp_identified") is True,
        "snapshot_linked": bool(board_id) and visual.get("board_snapshot_id") == board_id,
        "capture_session_linked": bool(board_session)
            and visual.get("capture_session_id") == board_session,
        "errors": errors,
        "blockers": list(errors),
        "verification_scope": (
            "Human-confirmed physical shooter-to-position identity for one capture frame; "
            "does not verify colour mapping, ammunition OCR, firing behaviour, or gameplay."
        ),
        "verified_by_user": identity_data.get("verified_by_user") is True,
        "gameplay_verified": False,
        "game_taps_enabled": False,
        "actions_performed": False,
    }


def build_report(board_path=BOARD_FILE, visual_path=VISUAL_FILE,
                 identity_path=IDENTITY_FILE, calibration_path=CALIBRATION_FILE,
                 detection_path=DETECTION_FILE):
    inputs = {
        "board_observation_json": board_path,
        "conveyor_visual_observations_json": visual_path,
        "shooter_identity_observations_json": identity_path,
        "conveyor_calibration_json": calibration_path,
        "shooter_detection_json": detection_path,
    }
    values = {}
    hashes = {}
    errors = []
    for key, path in inputs.items():
        try:
            values[key], hashes[key] = read_json_snapshot(path)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            values[key] = {}
            errors.append(f"{key}: {type(exc).__name__}: {exc}")
    result = audit_identity(
        values["board_observation_json"],
        values["conveyor_visual_observations_json"],
        values["shooter_identity_observations_json"],
        values["conveyor_calibration_json"],
        values["shooter_detection_json"],
        current_source_file_sha256={
            key: hashes.get(key)
            for key in (
                "board_observation_json",
                "conveyor_visual_observations_json",
                "conveyor_calibration_json",
                "shooter_detection_json",
            )
        },
    )
    if errors:
        result["errors"] = sorted(set(result["errors"] + errors))
        result["blockers"] = list(result["errors"])
        result["identity_verified"] = False
    result["source_file_sha256"] = hashes
    return result


def main(board_path=BOARD_FILE, output_path=OUTPUT_FILE):
    report = build_report(board_path=Path(board_path))
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(output_path.suffix + ".tmp")
    temporary.write_text(json.dumps(report, indent=2))
    temporary.replace(output_path)

    print("SLIME AI — HUMAN-CONFIRMED IDENTITY AUDIT")
    print("=" * 48)
    print("Identity verified:", report["identity_verified"])
    print("Positions checked:", report["positions_checked"])
    print("Known shooters:", len(report["known_shooters"]))
    for blocker in report["blockers"]:
        print("BLOCKED:", blocker)
    print("Gameplay verified: False")
    print("Game taps enabled: False")
    print("Report:", output_path)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Create a source-bound audit from user-confirmed identity observations"
    )
    parser.add_argument("--board", default=str(BOARD_FILE))
    parser.add_argument("--output", default=str(OUTPUT_FILE))
    args = parser.parse_args()
    main(args.board, args.output)
