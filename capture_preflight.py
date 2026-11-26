"""Fail-closed validation for a fresh board/shooter screenshot pair."""
import json
from strict_json import strict_json_loads
import re
from datetime import datetime
from pathlib import Path

from capture_provenance import (
    parse_aware_capture_timestamp,
    validate_capture_session_id,
)
from snapshot_sync import validate_capture_freshness
from source_pixel_audit import validate_source_pixel_audit_status


def _positive_int_pair(value):
    return (
        isinstance(value, list)
        and len(value) == 2
        and all(type(item) is int and item > 0 for item in value)
    )


def validate_capture_pair(
    observation_path,
    shooter_path,
    *,
    now=None,
    max_age_seconds=300,
    max_skew_seconds=120,
    pixel_audit_path=None,
    board_data=None,
    shooter_data=None,
    pixel_audit_data=None,
):
    """Validate paired capture provenance and recency without inferring truth."""
    observation_path = Path(observation_path)
    shooter_path = Path(shooter_path)
    try:
        if board_data is None:
            board_data = strict_json_loads(observation_path.read_bytes())
        if shooter_data is None:
            shooter_data = strict_json_loads(shooter_path.read_bytes())
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        return {"valid": False, "reason": f"Capture files are missing or invalid: {exc}"}
    board = board_data

    if not isinstance(board, dict) or not isinstance(shooter_data, dict):
        return {"valid": False, "reason": "Capture files must contain JSON objects."}

    # Recheck the safety/evidence contract at the point where a capture is
    # admitted for readiness. Stored files may have changed since capture.
    board_unverified_flags = (
        "same_board_state_confirmed",
        "gameplay_verified",
        "vision_classification_verified",
        "game_taps_enabled",
    )
    for flag in board_unverified_flags:
        if board.get(flag) is not False:
            return {
                "valid": False,
                "reason": f"Board observation {flag} must remain False.",
            }

    shooter_quality = shooter_data.get("observation_quality")
    if not isinstance(shooter_quality, dict):
        return {
            "valid": False,
            "reason": "Shooter observation_quality flags are missing.",
        }
    shooter_unverified_flags = (
        "colour_independently_verified",
        "ammunition_independently_verified",
        "slot_mapping_independently_verified",
    )
    for flag in shooter_unverified_flags:
        if shooter_quality.get(flag) is not False:
            return {
                "valid": False,
                "reason": f"Shooter observation {flag} must remain False.",
            }

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

    # A fresh matching pair is not sufficient: planning also requires the
    # independent pixel audit generated by the capture pipeline.
    audit_path = (
        Path(pixel_audit_path)
        if pixel_audit_path is not None
        else observation_path.parent / "source_pixel_audit_latest.json"
    )
    try:
        if pixel_audit_data is None:
            pixel_audit_data = strict_json_loads(audit_path.read_bytes())
    except (OSError, UnicodeDecodeError, ValueError):
        return {
            "valid": False,
            "reason": "Independent source-pixel audit is missing or invalid; rerun the capture pipeline.",
            "freshness": freshness,
        }
    pixel_audit = pixel_audit_data
    if not isinstance(pixel_audit, dict):
        return {
            "valid": False,
            "reason": "Independent source-pixel audit must be a JSON object.",
            "freshness": freshness,
        }
    try:
        validate_source_pixel_audit_status(pixel_audit)
    except ValueError as exc:
        return {
            "valid": False,
            "reason": str(exc),
            "freshness": freshness,
        }

    board_image_size = board.get("image_size")
    board_grid_size = board.get("grid_size")
    audit_image_size = pixel_audit.get("image_size")
    audit_grid_size = pixel_audit.get("grid_size")
    audit_label_mismatch_count = pixel_audit.get("label_mismatch_count")
    audit_schema_version = pixel_audit.get("schema_version")
    audit_sample_count = pixel_audit.get("sample_count")
    audit_reproduced_sample_count = pixel_audit.get("reproduced_sample_count")
    audit_pixel_mismatch_count = pixel_audit.get("pixel_sample_mismatch_count")
    expected_sample_count = (
        board_grid_size[0] * board_grid_size[1]
        if _positive_int_pair(board_grid_size) else None
    )
    audit_matches = (
        _positive_int_pair(board_image_size)
        and _positive_int_pair(board_grid_size)
        and _positive_int_pair(audit_image_size)
        and _positive_int_pair(audit_grid_size)
        and audit_image_size == board_image_size
        and audit_grid_size == board_grid_size
        and board_grid_size[0] <= 10_000
        and board_grid_size[1] <= 10_000
        and expected_sample_count <= 1_000_000
        and type(audit_schema_version) is int
        and audit_schema_version == 1
        and type(audit_sample_count) is int
        and audit_sample_count == expected_sample_count
        and type(audit_reproduced_sample_count) is int
        and audit_reproduced_sample_count == expected_sample_count
        and type(audit_pixel_mismatch_count) is int
        and audit_pixel_mismatch_count == 0
        and pixel_audit.get("pixel_sample_mismatches") == []
        and pixel_audit.get("label_mismatches") == []
        and type(audit_label_mismatch_count) is int
        and audit_label_mismatch_count == 0
        and pixel_audit.get("source_sha256") == source_hash
        and pixel_audit.get("capture_session_id") == board_session
        and pixel_audit.get("captured_at") == board.get("captured_at")
        and pixel_audit.get("snapshot_id") == board.get("snapshot_id")
        and pixel_audit.get("board_snapshot_id") == board.get("board_snapshot_id")
        and pixel_audit.get("pixel_samples_reproduced") is True
        and pixel_audit.get("extraction_fingerprint_match") is True
        and pixel_audit.get("colour_counts_match") is True
        and pixel_audit.get("gameplay_verified") is False
        and pixel_audit.get("game_taps_enabled") is False
    )
    if not audit_matches:
        return {
            "valid": False,
            "reason": "Independent source-pixel audit is incomplete, mismatched, or not tied to this screenshot; rerun the capture pipeline.",
            "freshness": freshness,
        }
    return {
        "valid": True,
        "reason": None,
        "freshness": freshness,
        "source_pixel_audit_verified": True,
        "board_data": board,
        "shooter_data": shooter_data,
        "pixel_audit_data": pixel_audit,
    }
