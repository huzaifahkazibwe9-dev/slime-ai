#!/usr/bin/env python3
"""Run board ingestion and shooter detection from one explicitly calibrated capture."""
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

from capture_provenance import (
    parse_aware_capture_timestamp,
    validate_capture_session_id,
)

BOARD_OUTPUT = Path("data/board_observation_latest.json")
SHOOTER_OUTPUT = Path("data/shooter_detection.json")


def load_capture_config(path):
    path = Path(path)
    data = json.loads(path.read_text())
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
    }


def validate_capture_outputs(board_path, shooter_path, expected_source_sha256,
                             expected_session_id, expected_captured_at):
    """Fail closed unless both stages prove they processed the same source bytes."""
    try:
        board = json.loads(Path(board_path).read_text())
        shooter = json.loads(Path(shooter_path).read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("Capture pipeline outputs are missing or invalid JSON") from exc

    if not isinstance(board, dict) or not isinstance(shooter, dict):
        raise ValueError("Capture pipeline outputs must be JSON objects")
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
    return True


def run_capture_pipeline(screenshot, config_path):
    screenshot = str(Path(screenshot).expanduser().resolve())
    config = load_capture_config(config_path)
    # Pin the expected digest before either subprocess reads the path. If the
    # file changes between stages, one or both outputs will fail this check.
    expected_source_sha256 = hashlib.sha256(Path(screenshot).read_bytes()).hexdigest()
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
    )


def main():
    parser = argparse.ArgumentParser(
        description="Ingest board and shooter evidence from one calibrated screenshot"
    )
    parser.add_argument("screenshot")
    parser.add_argument(
        "--config", default="data/shooter_capture_config.json"
    )
    args = parser.parse_args()
    run_capture_pipeline(args.screenshot, args.config)


if __name__ == "__main__":
    main()
