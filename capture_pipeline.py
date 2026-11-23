#!/usr/bin/env python3
"""Run board ingestion and shooter detection from one explicitly calibrated capture."""
import argparse
import json
import subprocess
import sys
from pathlib import Path

from capture_provenance import (
    parse_aware_capture_timestamp,
    validate_capture_session_id,
)


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


def run_capture_pipeline(screenshot, config_path):
    screenshot = str(Path(screenshot).expanduser().resolve())
    config = load_capture_config(config_path)
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
