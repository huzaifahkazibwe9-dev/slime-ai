#!/usr/bin/env python3
"""Run board ingestion and shooter detection from one explicitly calibrated capture."""
import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

from capture_provenance import (
    parse_aware_capture_timestamp,
    validate_capture_session_id,
)
from source_pixel_audit import audit_source_pixels
from strict_json import strict_json_loads

BOARD_OUTPUT = Path("data/board_observation_latest.json")
SHOOTER_OUTPUT = Path("data/shooter_detection.json")
PIXEL_AUDIT_OUTPUT = Path("data/source_pixel_audit_latest.json")


def load_capture_config(path):
    path = Path(path)
    config_bytes = path.read_bytes()
    config_sha256 = hashlib.sha256(config_bytes).hexdigest()
    try:
        data = strict_json_loads(config_bytes)
    except (UnicodeDecodeError, ValueError) as exc:
        raise ValueError("Capture config is not valid UTF-8 JSON") from exc
    if not isinstance(data, dict):
        raise ValueError("Capture config must be a JSON object")
    bounds = data.get("panel_bounds")
    if (not isinstance(bounds, list) or len(bounds) != 4
            or any(type(value) is not int for value in bounds)):
        raise ValueError("panel_bounds must contain four integer coordinates")
    session = validate_capture_session_id(data.get("capture_session_id"))
    if session is None:
        raise ValueError("capture_session_id is required")
    captured_at = parse_aware_capture_timestamp(data.get("captured_at"))
    if captured_at is None:
        raise ValueError("captured_at with a UTC offset is required")
    return {
        "panel_bounds": bounds,
        "capture_session_id": session,
        "captured_at": captured_at,
        "config_sha256": config_sha256,
    }


def validate_capture_outputs(board_path, shooter_path, expected_source_sha256,
                             expected_session_id, expected_captured_at,
                             expected_config_sha256=None, expected_panel_bounds=None):
    """Fail closed unless both stages prove they processed the same source bytes."""
    try:
        board = strict_json_loads(Path(board_path).read_bytes())
        shooter = strict_json_loads(Path(shooter_path).read_bytes())
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise ValueError("Capture pipeline outputs are missing or invalid JSON") from exc

    if not isinstance(board, dict) or not isinstance(shooter, dict):
        raise ValueError("Capture pipeline outputs must be JSON objects")

    # Capture is observation only. Require explicit false values rather than
    # allowing absent, null, or truthy flags to be interpreted as verified.
    board_unverified_flags = (
        "same_board_state_confirmed",
        "gameplay_verified",
        "vision_classification_verified",
        "game_taps_enabled",
    )
    for flag in board_unverified_flags:
        if board.get(flag) is not False:
            raise ValueError(
                f"Board observation {flag} must remain False during capture"
            )

    quality = shooter.get("observation_quality")
    if not isinstance(quality, dict):
        raise ValueError("Shooter output is missing observation_quality flags")
    shooter_unverified_flags = (
        "colour_independently_verified",
        "ammunition_independently_verified",
        "slot_mapping_independently_verified",
    )
    for flag in shooter_unverified_flags:
        if quality.get(flag) is not False:
            raise ValueError(
                f"Shooter observation {flag} must remain False during capture"
            )

    provenance = shooter.get("capture_provenance")
    if not isinstance(provenance, dict):
        raise ValueError("Shooter output is missing capture provenance")

    if board.get("source_sha256") != expected_source_sha256:
        raise ValueError("Board observation does not match the input screenshot snapshot")
    if provenance.get("source_sha256") != expected_source_sha256:
        raise ValueError("Shooter observation does not match the input screenshot snapshot")
    if board.get("snapshot_id") != "sha256:" + expected_source_sha256:
        raise ValueError("Board snapshot identifier does not match its source hash")
    if board.get("board_snapshot_id") != "sha256:" + expected_source_sha256:
        raise ValueError("Board snapshot identifier is inconsistent")
    if board.get("capture_session_id") != expected_session_id:
        raise ValueError("Board capture session does not match the requested session")
    if provenance.get("capture_session_id") != expected_session_id:
        raise ValueError("Shooter capture session does not match the requested session")
    if board.get("captured_at") != expected_captured_at:
        raise ValueError("Board capture timestamp does not match the requested timestamp")
    if provenance.get("captured_at") != expected_captured_at:
        raise ValueError("Shooter capture timestamp does not match the requested timestamp")
    if provenance.get("verified") is not True:
        raise ValueError("Shooter capture provenance is not verified")
    if expected_config_sha256 is not None:
        if provenance.get("capture_config_sha256") != expected_config_sha256:
            raise ValueError("Shooter capture config hash does not match the parsed config bytes")
    if expected_panel_bounds is not None:
        if provenance.get("panel_bounds") != expected_panel_bounds:
            raise ValueError("Shooter panel bounds do not match the parsed capture config")

    # Bonded relationships are sourced from a separate user-confirmed file.
    # Require the detector to identify that source and fingerprint the exact
    # bytes it parsed; otherwise the shooter record has incomplete provenance.
    bonding_source = shooter.get("bonding_source")
    bonding_digest = shooter.get("bonding_config_sha256")
    if bonding_source not in {"user_confirmed", "not_user_confirmed", "not_configured"}:
        raise ValueError("Shooter output has an invalid bonded-group source")
    if bonding_source == "not_configured":
        if bonding_digest is not None:
            raise ValueError("Unconfigured bonded-group source must not have a digest")
    elif (
        not isinstance(bonding_digest, str)
        or re.fullmatch(r"[0-9a-f]{64}", bonding_digest) is None
    ):
        raise ValueError("Bonded-group config is missing its exact SHA-256 provenance")
    return True


def audit_capture_pixels(board_path, source_image_bytes, output_path=PIXEL_AUDIT_OUTPUT):
    """Require independently reproduced source pixels before accepting capture."""
    try:
        observation = strict_json_loads(Path(board_path).read_bytes())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Board observation is missing or invalid for pixel audit") from exc
    report = audit_source_pixels(observation, source_image_bytes)
    # Bind the audit to this exact capture, not only its image hash. Identical
    # screenshot bytes can recur across separate capture sessions.
    report.update({
        "capture_session_id": observation.get("capture_session_id"),
        "captured_at": observation.get("captured_at"),
        "snapshot_id": observation.get("snapshot_id"),
        "board_snapshot_id": observation.get("board_snapshot_id"),
    })
    if report.get("pixel_samples_reproduced") is not True:
        raise ValueError("Independent source-pixel audit found RGB sample mismatches")
    if report.get("extraction_fingerprint_match") is not True:
        raise ValueError("Independent source-pixel audit found a missing or mismatched extraction fingerprint")
    if type(report.get("label_mismatch_count")) is not int or report.get("label_mismatch_count") != 0:
        raise ValueError("Board labels do not match labels derived from source RGB samples")
    if report.get("colour_counts_match") is not True:
        raise ValueError("Board colour counts do not match the extracted board labels")

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(json.dumps(report, indent=2), encoding="utf-8")
    temporary.replace(output)
    return report


def run_capture_pipeline(screenshot, config_path):
    screenshot = str(Path(screenshot).expanduser().resolve())
    config = load_capture_config(config_path)
    # Preserve one immutable byte snapshot for hashing and independent audit.
    source_image_bytes = Path(screenshot).read_bytes()
    expected_source_sha256 = hashlib.sha256(source_image_bytes).hexdigest()
    common = [
        "--capture-session-id", config["capture_session_id"],
        "--captured-at", config["captured_at"],
    ]
    subprocess.run(
        [sys.executable, "screenshot_ingestor.py", screenshot, *common],
        check=True,
    )
    subprocess.run(
        [
            sys.executable, "shooter_detector.py",
            "--source-screenshot", screenshot,
            "--panel-bounds", *map(str, config["panel_bounds"]),
            "--extract-panel",
            "--capture-config-sha256", config["config_sha256"],
            *common,
        ],
        check=True,
    )
    validate_capture_outputs(
        BOARD_OUTPUT,
        SHOOTER_OUTPUT,
        expected_source_sha256,
        config["capture_session_id"],
        config["captured_at"],
        config["config_sha256"],
        config["panel_bounds"],
    )
    return audit_capture_pixels(BOARD_OUTPUT, source_image_bytes)


def main():
    parser = argparse.ArgumentParser(
        description="Ingest board and shooter evidence from one calibrated screenshot"
    )
    parser.add_argument("screenshot")
    parser.add_argument(
        "--config", default="data/shooter_capture_config.json"
    )
    args = parser.parse_args()
    report = run_capture_pipeline(args.screenshot, args.config)
    print("Independent source-pixel audit passed:", report["pixel_samples_reproduced"])
    print("Extraction fingerprint matched:", report["extraction_fingerprint_match"])
    print("Calibration alignment verified: False")
    print("Gameplay verified: False")
    print("Game taps enabled: False")


if __name__ == "__main__":
    main()
