"""Fail-closed validation for a fresh board/shooter screenshot pair."""
import json
import re
from datetime import datetime
from pathlib import Path

from capture_provenance import (
    parse_aware_capture_timestamp,
    validate_capture_session_id,
)
from snapshot_sync import validate_capture_freshness


def validate_capture_pair(
    observation_path,
    shooter_path,
    *,
    now=None,
    max_age_seconds=300,
    max_skew_seconds=120,
):
    """Validate paired capture provenance and recency without inferring truth."""
    observation_path = Path(observation_path)
    shooter_path = Path(shooter_path)
    try:
        board = json.loads(observation_path.read_text(encoding="utf-8"))
        shooter_data = json.loads(shooter_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"valid": False, "reason": f"Capture files are missing or invalid: {exc}"}

    if not isinstance(board, dict) or not isinstance(shooter_data, dict):
        return {"valid": False, "reason": "Capture files must contain JSON objects."}

    provenance = shooter_data.get("capture_provenance")
    if not isinstance(provenance, dict) or provenance.get("verified") is not True:
        return {"valid": False, "reason": "Shooter capture provenance is not verified."}

    source_hash = board.get("source_sha256")
    if (
        not isinstance(source_hash, str)
        or re.fullmatch(r"[0-9a-f]{64}", source_hash) is None
        or provenance.get("source_sha256") != source_hash
    ):
        return {"valid": False, "reason": "Board and shooter evidence do not share a valid screenshot hash."}

    expected_snapshot_id = "sha256:" + source_hash
    if (
        board.get("snapshot_id") != expected_snapshot_id
        or board.get("board_snapshot_id") != expected_snapshot_id
    ):
        return {"valid": False, "reason": "Board snapshot identifiers do not match the screenshot hash."}

    try:
        board_session = validate_capture_session_id(board.get("capture_session_id"))
        shooter_session = validate_capture_session_id(
            provenance.get("capture_session_id")
        )
        board_time = parse_aware_capture_timestamp(board.get("captured_at"))
        shooter_time = parse_aware_capture_timestamp(provenance.get("captured_at"))
    except ValueError as exc:
        return {"valid": False, "reason": f"Capture metadata is invalid: {exc}"}

    if not board_session or board_session != shooter_session:
        return {"valid": False, "reason": "Board and shooter evidence do not share a valid capture session."}
    if not board_time or not shooter_time:
        return {"valid": False, "reason": "Both capture timestamps must include a UTC offset."}
    if datetime.fromisoformat(board_time) != datetime.fromisoformat(shooter_time):
        return {"valid": False, "reason": "Board and shooter evidence do not share a capture timestamp."}

    freshness = validate_capture_freshness(
        board_time,
        shooter_time,
        now=now,
        max_age_seconds=max_age_seconds,
        max_skew_seconds=max_skew_seconds,
    )
    if freshness.get("fresh") is not True:
        return {
            "valid": False,
            "reason": "Screenshot capture is stale or timestamps are misaligned; run the capture pipeline again.",
            "freshness": freshness,
        }
    return {"valid": True, "reason": None, "freshness": freshness}
