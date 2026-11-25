#!/usr/bin/env python3
"""Prepare board-colour and shooter review templates from one verified capture.

The two blank templates are tied to the same immutable screenshot. A manifest
records their hashes and the hashes of the exact upstream capture artifacts.
Nothing in this workflow marks human labels as complete or gameplay as verified.
"""
import argparse
from io import BytesIO
import hashlib
import json
from pathlib import Path

from PIL import Image

from capture_pipeline import (
    BOARD_OUTPUT,
    PIXEL_AUDIT_OUTPUT,
    SHOOTER_OUTPUT,
    run_capture_pipeline,
)
from prepare_colour_labels import build_template as build_colour_template
from prepare_shooter_labels import build_template as build_shooter_template
from source_pixel_audit import validate_source_pixel_audit_status
from strict_json import strict_json_loads


def _read_json_object(path, description):
    path = Path(path)
    try:
        raw = path.read_bytes()
        data = strict_json_loads(raw)
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise ValueError(f"{description} is missing or invalid JSON") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{description} must be a JSON object")
    return data, raw, hashlib.sha256(raw).hexdigest()


def _json_bytes(data):
    return json.dumps(data, indent=2, sort_keys=True).encode("utf-8")


def _write_atomic(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(content)
    temporary.replace(path)


def prepare_visual_review_bundle(
    screenshot,
    config_path="data/shooter_capture_config.json",
    board_template_path="data/colour_labels_template.json",
    shooter_template_path="data/shooter_labels_template.json",
    manifest_path="data/visual_review_bundle.json",
):
    """Capture once, then build two source-bound blank review templates."""
    screenshot_path = Path(screenshot).expanduser().resolve()

    # This runs both extractors and requires the independent source-pixel audit.
    capture_report = run_capture_pipeline(screenshot_path, config_path)
    if not isinstance(capture_report, dict):
        raise ValueError("Capture pipeline did not return an audit report")
    validate_source_pixel_audit_status(capture_report)
    if capture_report.get("pixel_samples_reproduced") is not True:
        raise ValueError("Capture pipeline did not independently reproduce board pixels")
    if capture_report.get("extraction_fingerprint_match") is not True:
        raise ValueError("Capture pipeline extraction fingerprint did not match")
    if type(capture_report.get("label_mismatch_count")) is not int:
        raise ValueError("Capture pipeline label mismatch count is invalid")
    if capture_report["label_mismatch_count"] != 0:
        raise ValueError("Capture pipeline found board label mismatches")
    if capture_report.get("colour_counts_match") is not True:
        raise ValueError("Capture pipeline colour counts did not match")

    # The path is read again only after capture; the hash comparison detects
    # replacement between pipeline completion and review-template generation.
    try:
        screenshot_bytes = screenshot_path.read_bytes()
        with Image.open(BytesIO(screenshot_bytes)) as image:
            screenshot_size = list(image.size)
    except (OSError, ValueError) as exc:
        raise ValueError("Source screenshot is missing or unreadable") from exc
    screenshot_sha256 = hashlib.sha256(screenshot_bytes).hexdigest()
    if screenshot_sha256 != capture_report.get("source_sha256"):
        raise ValueError("Source screenshot changed after the verified capture pipeline")

    board, board_bytes, board_digest = _read_json_object(
        BOARD_OUTPUT, "Board observation"
    )
    shooter, shooter_bytes, shooter_digest = _read_json_object(
        SHOOTER_OUTPUT, "Shooter detection"
    )
    pixel_audit, audit_bytes, audit_digest = _read_json_object(
        PIXEL_AUDIT_OUTPUT, "Source-pixel audit"
    )
    validate_source_pixel_audit_status(pixel_audit)

    if board.get("source_sha256") != screenshot_sha256:
        raise ValueError("Board observation belongs to a different screenshot")
    if board.get("image_size") != screenshot_size:
        raise ValueError("Board observation image dimensions do not match screenshot")
    if pixel_audit.get("source_sha256") != screenshot_sha256:
        raise ValueError("Source-pixel audit belongs to a different screenshot")
    if pixel_audit.get("pixel_samples_reproduced") is not True:
        raise ValueError("Persisted source-pixel audit did not reproduce every sample")
    if pixel_audit.get("extraction_fingerprint_match") is not True:
        raise ValueError("Persisted source-pixel audit fingerprint did not match")
    if type(pixel_audit.get("label_mismatch_count")) is not int:
        raise ValueError("Persisted source-pixel audit mismatch count is invalid")
    if pixel_audit.get("label_mismatch_count") != 0:
        raise ValueError("Persisted source-pixel audit found label mismatches")
    if pixel_audit.get("colour_counts_match") is not True:
        raise ValueError("Persisted source-pixel audit colour counts did not match")

    capture = shooter.get("capture_provenance")
    if not isinstance(capture, dict):
        raise ValueError("Shooter detection is missing capture provenance")
    session_id = board.get("capture_session_id")
    captured_at = board.get("captured_at")
    if not isinstance(session_id, str) or not session_id:
        raise ValueError("Board observation is missing capture_session_id")
    if not isinstance(captured_at, str) or not captured_at:
        raise ValueError("Board observation is missing captured_at")
    if capture.get("source_sha256") != screenshot_sha256:
        raise ValueError("Shooter detection belongs to a different screenshot")
    if capture.get("capture_session_id") != session_id:
        raise ValueError("Board and shooter captures have different session IDs")
    if capture.get("captured_at") != captured_at:
        raise ValueError("Board and shooter captures have different timestamps")
    for key in ("capture_session_id", "captured_at", "snapshot_id", "board_snapshot_id"):
        if pixel_audit.get(key) != board.get(key):
            raise ValueError(f"Source-pixel audit {key} does not match board observation")

    colour_template = build_colour_template(board)
    if colour_template.get("source_sha256") != screenshot_sha256:
        raise ValueError("Board review template is not bound to the source screenshot")
    if colour_template.get("image_size") != screenshot_size:
        raise ValueError("Board review template dimensions do not match source screenshot")

    shooter_template = build_shooter_template(
        shooter, shooter_bytes, screenshot_bytes
    )
    if shooter_template.get("source_screenshot_sha256") != screenshot_sha256:
        raise ValueError("Shooter review template is not bound to the source screenshot")
    if shooter_template.get("source_detection_sha256") != shooter_digest:
        raise ValueError("Shooter review template is not bound to the exact detector JSON")
    if shooter_template.get("capture_provenance", {}).get("capture_session_id") != session_id:
        raise ValueError("Shooter review template capture identity does not match board capture")

    colour_bytes = _json_bytes(colour_template)
    shooter_template_bytes = _json_bytes(shooter_template)
    manifest = {
        "schema_version": 1,
        "review_status": "NOT_REVIEWED",
        "labelled_by_user": False,
        "source_screenshot_sha256": screenshot_sha256,
        "source_screenshot_size": screenshot_size,
        "capture_session_id": session_id,
        "captured_at": captured_at,
        "source_artifacts_sha256": {
            "board_observation_json": board_digest,
            "shooter_detection_json": shooter_digest,
            "source_pixel_audit_json": audit_digest,
        },
        "review_templates": {
            "board_colour": {
                "file": Path(board_template_path).name,
                "sha256": hashlib.sha256(colour_bytes).hexdigest(),
                "sample_count": len(colour_template["samples"]),
            },
            "shooter_observation": {
                "file": Path(shooter_template_path).name,
                "sha256": hashlib.sha256(shooter_template_bytes).hexdigest(),
                "sample_count": len(shooter_template["samples"]),
            },
        },
        "limitations": [
            "Templates contain no human labels and are not evaluation-ready.",
            "Matching hashes establish artifact identity, not visual-label truth.",
            "Shooter colour, ammunition and slot mapping remain unverified.",
            "Gameplay is not verified and game taps remain disabled.",
        ],
    }
    manifest["bundle_sha256"] = hashlib.sha256(_json_bytes(manifest)).hexdigest()
    manifest_bytes = _json_bytes(manifest)

    # Write the manifest last: its presence indicates both template files were
    # successfully written in this run.
    _write_atomic(board_template_path, colour_bytes)
    _write_atomic(shooter_template_path, shooter_template_bytes)
    _write_atomic(manifest_path, manifest_bytes)

    return manifest


def main():
    parser = argparse.ArgumentParser(
        description="Prepare board and shooter human-review templates from one verified screenshot"
    )
    parser.add_argument("screenshot", help="Original game screenshot")
    parser.add_argument("--config", default="data/shooter_capture_config.json")
    parser.add_argument("--board-output", default="data/colour_labels_template.json")
    parser.add_argument("--shooter-output", default="data/shooter_labels_template.json")
    parser.add_argument("--manifest-output", default="data/visual_review_bundle.json")
    args = parser.parse_args()

    manifest = prepare_visual_review_bundle(
        args.screenshot,
        args.config,
        args.board_output,
        args.shooter_output,
        args.manifest_output,
    )
    print("SLIME AI — VERIFIED VISUAL REVIEW BUNDLE")
    print("=" * 46)
    print("Capture session:", manifest["capture_session_id"])
    print("Source screenshot SHA256:", manifest["source_screenshot_sha256"])
    print("Board samples:", manifest["review_templates"]["board_colour"]["sample_count"])
    print("Shooter samples:", manifest["review_templates"]["shooter_observation"]["sample_count"])
    print("Human review complete: False")
    print("Evaluation-ready: False")
    print("Gameplay verified: False")
    print("Game taps enabled: False")
    print("Manifest:", args.manifest_output)


if __name__ == "__main__":
    main()
