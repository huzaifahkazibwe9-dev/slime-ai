#!/usr/bin/env python3
"""Evaluate board-colour and shooter reviews from one source-bound capture.

This is a combined orchestration layer. It verifies the review manifest and
source artifacts, independently reproduces board RGB samples from the original
screenshot, then invokes the existing specialist evaluators.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path

from PIL import Image
from io import BytesIO

from screenshot_ingestor import classify_rgb
from source_pixel_audit import audit_source_pixels
from vision_calibration import evaluate_dataset as evaluate_colour_dataset
from vision_calibration import validate_dataset as validate_colour_dataset
from vision_calibration import verify_source_image
from shooter_observation_evaluation import (
    evaluate_dataset as evaluate_shooter_dataset,
    verify_source_artifacts as verify_shooter_source_artifacts,
)
from prepare_colour_labels import build_template as build_colour_template
from prepare_shooter_labels import build_template as build_shooter_template
from capture_provenance import (
    parse_aware_capture_timestamp,
    validate_capture_session_id,
)


def _sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def _read_bytes(path, description):
    try:
        return Path(path).read_bytes()
    except OSError as exc:
        raise ValueError(f"{description} is missing or unreadable") from exc


def _read_json_object(path, description):
    raw = _read_bytes(path, description)
    try:
        data = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{description} is not valid UTF-8 JSON") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{description} must be a JSON object")
    return data, raw


def _canonical_json_bytes(data):
    return json.dumps(data, indent=2, sort_keys=True).encode("utf-8")


def verify_manifest(manifest):
    """Verify the exact schema-v1 manifest structure and its self-digest."""
    if not isinstance(manifest, dict):
        raise ValueError("Review manifest must be a JSON object")
    expected_fields = {
        "schema_version",
        "review_status",
        "labelled_by_user",
        "source_screenshot_sha256",
        "source_screenshot_size",
        "capture_session_id",
        "captured_at",
        "source_artifacts_sha256",
        "review_templates",
        "limitations",
        "bundle_sha256",
    }
    if set(manifest) != expected_fields:
        raise ValueError("Review manifest fields do not match schema-v1")
    if type(manifest.get("schema_version")) is not int or manifest["schema_version"] != 1:
        raise ValueError("Review manifest schema_version must be 1")
    if manifest.get("review_status") != "NOT_REVIEWED":
        raise ValueError("Review manifest review_status must remain NOT_REVIEWED")
    if manifest.get("labelled_by_user") is not False:
        raise ValueError("Review manifest must not claim human labels are complete")

    screenshot_hash = manifest.get("source_screenshot_sha256")
    if (
        not isinstance(screenshot_hash, str)
        or len(screenshot_hash) != 64
        or any(character not in "0123456789abcdef" for character in screenshot_hash)
    ):
        raise ValueError("Review manifest source_screenshot_sha256 is invalid")
    screenshot_size = manifest.get("source_screenshot_size")
    if (
        not isinstance(screenshot_size, list)
        or len(screenshot_size) != 2
        or any(type(value) is not int or value < 1 for value in screenshot_size)
    ):
        raise ValueError("Review manifest source_screenshot_size is invalid")
    session_id = manifest.get("capture_session_id")
    if not isinstance(session_id, str) or not session_id.strip():
        raise ValueError("Review manifest capture_session_id is invalid")
    try:
        if validate_capture_session_id(session_id) != session_id:
            raise ValueError("Capture session ID is not canonical")
    except ValueError as exc:
        raise ValueError("Review manifest capture_session_id is invalid") from exc
    captured_at = manifest.get("captured_at")
    if not isinstance(captured_at, str) or not captured_at.strip():
        raise ValueError("Review manifest captured_at is invalid")
    try:
        if parse_aware_capture_timestamp(captured_at) != captured_at:
            raise ValueError("Capture timestamp is not canonical")
    except ValueError as exc:
        raise ValueError(
            "Review manifest captured_at must be canonical ISO-8601 with a UTC offset"
        ) from exc

    limitations = manifest.get("limitations")
    if (
        not isinstance(limitations, list)
        or not limitations
        or any(not isinstance(item, str) or not item.strip() for item in limitations)
    ):
        raise ValueError("Review manifest limitations must be a non-empty list of strings")

    digest = manifest.get("bundle_sha256")
    if (
        not isinstance(digest, str)
        or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
    ):
        raise ValueError("Review manifest bundle_sha256 is invalid")
    unsigned = {key: value for key, value in manifest.items() if key != "bundle_sha256"}
    expected = _sha256(_canonical_json_bytes(unsigned))
    if digest != expected:
        raise ValueError("Review manifest bundle_sha256 does not match its contents")

    artifacts = manifest.get("source_artifacts_sha256")
    expected_artifact_fields = {
        "board_observation_json",
        "shooter_detection_json",
        "source_pixel_audit_json",
    }
    if not isinstance(artifacts, dict) or set(artifacts) != expected_artifact_fields:
        raise ValueError("Review manifest source_artifacts_sha256 fields are invalid")
    for key, value in artifacts.items():
        if (
            not isinstance(value, str)
            or len(value) != 64
            or any(character not in "0123456789abcdef" for character in value)
        ):
            raise ValueError(f"Review manifest {key} digest is invalid")

    templates = manifest.get("review_templates")
    expected_template_fields = {"board_colour", "shooter_observation"}
    if not isinstance(templates, dict) or set(templates) != expected_template_fields:
        raise ValueError("Review manifest review_templates fields are invalid")
    for key, entry in templates.items():
        if not isinstance(entry, dict) or set(entry) != {"file", "sha256", "sample_count"}:
            raise ValueError(f"Review manifest {key} template fields are invalid")
        filename = entry.get("file")
        template_digest = entry.get("sha256")
        count = entry.get("sample_count")
        if not isinstance(filename, str) or not filename or Path(filename).name != filename:
            raise ValueError(f"Review manifest {key} template filename is invalid")
        if (
            not isinstance(template_digest, str)
            or len(template_digest) != 64
            or any(character not in "0123456789abcdef" for character in template_digest)
        ):
            raise ValueError(f"Review manifest {key} template digest is invalid")
        if type(count) is not int or count < 1:
            raise ValueError(f"Review manifest {key} sample_count is invalid")
    return True


def _verify_colour_samples(dataset, board_observation):
    """Ensure reviewed RGB values still equal the pinned board-observation RGBs."""
    validated = validate_colour_dataset(dataset)
    raw_rgb = board_observation.get("raw_rgb")
    grid = board_observation.get("grid_size")
    if (not isinstance(grid, list) or len(grid) != 2
            or any(type(value) is not int or value < 1 for value in grid)):
        raise ValueError("Source board observation grid_size is invalid")
    columns, rows = grid
    if (not isinstance(raw_rgb, list) or len(raw_rgb) != rows
            or any(not isinstance(row, list) or len(row) != columns for row in raw_rgb)):
        raise ValueError("Source board observation raw_rgb shape does not match grid_size")
    if len(validated) != columns * rows:
        raise ValueError("Reviewed board dataset must cover every source board cell exactly once")
    coordinates = set()
    source_samples = {sample["id"]: sample for sample in dataset["samples"]}
    for sample in validated:
        row, column = sample.get("row"), sample.get("column")
        if type(row) is not int or type(column) is not int:
            raise ValueError("Reviewed board samples require zero-based row and column")
        coordinate = (row, column)
        if coordinate in coordinates:
            raise ValueError("Reviewed board dataset contains duplicate cell coordinates")
        coordinates.add(coordinate)
        if raw_rgb[row][column] != sample["rgb"]:
            raise ValueError(
                f"Reviewed board RGB for sample {sample['id']} differs from source observation"
            )
        original = source_samples[sample["id"]]
        expected_id = f"r{row + 1:02d}c{column + 1:02d}"
        if sample["id"] != expected_id or original.get("row") != row or original.get("column") != column:
            raise ValueError(f"Reviewed board sample identity does not match source cell {expected_id}")
    expected_coordinates = {(row, column) for row in range(rows) for column in range(columns)}
    if coordinates != expected_coordinates:
        raise ValueError("Reviewed board dataset does not cover the full source grid")
    return {
        "sample_count": len(validated),
        "source_rgb_values_match": True,
        "full_grid_coverage": True,
    }


def _verify_review_template_baselines(
    manifest,
    board_labels,
    shooter_labels,
    board_observation,
    shooter_detection,
    shooter_detection_bytes,
    screenshot_bytes,
):
    """Allow edits only in human annotation fields, preserving template provenance."""
    expected_board = build_colour_template(board_observation)
    board_candidate = copy.deepcopy(board_labels)
    if not isinstance(board_candidate.get("samples"), list):
        raise ValueError("Board review template samples are invalid")
    if len(board_candidate["samples"]) != len(expected_board["samples"]):
        raise ValueError("Board review template no longer matches its blank baseline")
    board_candidate["labelled_by_user"] = False
    for index, expected_sample in enumerate(expected_board["samples"]):
        sample = board_candidate["samples"][index]
        if not isinstance(sample, dict) or sample.get("id") != expected_sample["id"]:
            raise ValueError("Board review template sample identity/order changed")
        sample["label"] = ""
    if _canonical_json_bytes(board_candidate) != _canonical_json_bytes(expected_board):
        raise ValueError("Board review template metadata changed outside human label fields")

    expected_shooter = build_shooter_template(
        shooter_detection, shooter_detection_bytes, screenshot_bytes
    )
    shooter_candidate = copy.deepcopy(shooter_labels)
    if not isinstance(shooter_candidate.get("samples"), list):
        raise ValueError("Shooter review template samples are invalid")
    if len(shooter_candidate["samples"]) != len(expected_shooter["samples"]):
        raise ValueError("Shooter review template no longer matches its blank baseline")
    shooter_candidate["labelled_by_user"] = False
    for index, expected_sample in enumerate(expected_shooter["samples"]):
        sample = shooter_candidate["samples"][index]
        if not isinstance(sample, dict):
            raise ValueError(f"Shooter review sample {index} must be an object")
        if sample.get("detector") != expected_sample["detector"]:
            raise ValueError(f"Shooter review detector snapshot {index} changed")
        sample["review_status"] = expected_sample["review_status"]
        sample["human"] = copy.deepcopy(expected_sample["human"])
    if _canonical_json_bytes(shooter_candidate) != _canonical_json_bytes(expected_shooter):
        raise ValueError("Shooter review template metadata changed outside human annotation fields")

    records = manifest["review_templates"]
    expected_board_hash = _sha256(_canonical_json_bytes(expected_board))
    expected_shooter_hash = _sha256(_canonical_json_bytes(expected_shooter))
    if records["board_colour"]["sha256"] != expected_board_hash:
        raise ValueError("Manifest board template hash does not match reconstructed blank template")
    if records["shooter_observation"]["sha256"] != expected_shooter_hash:
        raise ValueError("Manifest shooter template hash does not match reconstructed blank template")
    return {
        "board_template_baseline_matched": True,
        "shooter_template_baseline_matched": True,
        "human_annotation_fields_only_changed": True,
    }


def evaluate_visual_review_bundle(
    manifest_path,
    board_labels_path,
    shooter_labels_path,
    board_observation_path,
    shooter_detection_path,
    pixel_audit_path,
    source_screenshot_path,
):
    """Verify one review bundle and return separate board/shooter metrics."""
    manifest, manifest_bytes = _read_json_object(manifest_path, "Visual review manifest")
    verify_manifest(manifest)

    board_labels, board_label_bytes = _read_json_object(board_labels_path, "Board-colour labels")
    shooter_labels, shooter_label_bytes = _read_json_object(shooter_labels_path, "Shooter labels")
    board_observation, board_bytes = _read_json_object(board_observation_path, "Board observation")
    shooter_detection, shooter_bytes = _read_json_object(shooter_detection_path, "Shooter detection")
    persisted_audit, audit_bytes = _read_json_object(pixel_audit_path, "Source-pixel audit")
    screenshot_bytes = _read_bytes(source_screenshot_path, "Original screenshot")

    actual_screenshot_hash = _sha256(screenshot_bytes)
    actual_artifact_hashes = {
        "board_observation_json": _sha256(board_bytes),
        "shooter_detection_json": _sha256(shooter_bytes),
        "source_pixel_audit_json": _sha256(audit_bytes),
    }
    if manifest.get("source_screenshot_sha256") != actual_screenshot_hash:
        raise ValueError("Original screenshot hash does not match review manifest")
    if manifest.get("source_artifacts_sha256") != actual_artifact_hashes:
        raise ValueError("One or more source artifact hashes do not match review manifest")

    try:
        with Image.open(BytesIO(screenshot_bytes)) as image:
            screenshot_size = list(image.size)
    except Exception as exc:
        raise ValueError("Original screenshot is not a readable image") from exc
    if manifest.get("source_screenshot_size") != screenshot_size:
        raise ValueError("Original screenshot dimensions do not match review manifest")

    session_id = manifest.get("capture_session_id")
    captured_at = manifest.get("captured_at")
    if not isinstance(session_id, str) or not session_id:
        raise ValueError("Review manifest capture_session_id is invalid")
    if not isinstance(captured_at, str) or not captured_at:
        raise ValueError("Review manifest captured_at is invalid")
    if (board_observation.get("capture_session_id") != session_id
            or board_observation.get("captured_at") != captured_at):
        raise ValueError("Board observation capture identity does not match manifest")
    shooter_capture = shooter_detection.get("capture_provenance")
    if not isinstance(shooter_capture, dict):
        raise ValueError("Shooter detection is missing capture provenance")
    if (shooter_capture.get("capture_session_id") != session_id
            or shooter_capture.get("captured_at") != captured_at
            or shooter_capture.get("source_sha256") != actual_screenshot_hash):
        raise ValueError("Shooter detection capture identity does not match manifest")
    for key in ("capture_session_id", "captured_at", "snapshot_id", "board_snapshot_id"):
        if persisted_audit.get(key) != board_observation.get(key):
            raise ValueError(f"Persisted pixel-audit {key} does not match board observation")

    required_template_records = manifest["review_templates"]
    if Path(board_labels_path).name != required_template_records["board_colour"]["file"]:
        raise ValueError("Board label file name does not match review manifest")
    if Path(shooter_labels_path).name != required_template_records["shooter_observation"]["file"]:
        raise ValueError("Shooter label file name does not match review manifest")
    if len(board_labels.get("samples", [])) != required_template_records["board_colour"]["sample_count"]:
        raise ValueError("Board label sample count does not match review manifest")
    if len(shooter_labels.get("samples", [])) != required_template_records["shooter_observation"]["sample_count"]:
        raise ValueError("Shooter label sample count does not match review manifest")

    if board_labels.get("source_sha256") != actual_screenshot_hash:
        raise ValueError("Board labels belong to a different screenshot")
    if board_labels.get("image_size") != screenshot_size:
        raise ValueError("Board label image dimensions do not match screenshot")
    if board_labels.get("grid_size") != board_observation.get("grid_size"):
        raise ValueError("Board label grid dimensions do not match source observation")
    if board_observation.get("source_sha256") != actual_screenshot_hash:
        raise ValueError("Board observation belongs to a different screenshot")
    if board_observation.get("image_size") != screenshot_size:
        raise ValueError("Board observation dimensions do not match screenshot")

    pixel_audit = audit_source_pixels(board_observation, screenshot_bytes)
    if pixel_audit.get("pixel_samples_reproduced") is not True:
        raise ValueError("Independent source-pixel audit did not reproduce every board RGB sample")
    if pixel_audit.get("extraction_fingerprint_match") is not True:
        raise ValueError("Independent source-pixel audit extraction fingerprint did not match")
    if type(pixel_audit.get("label_mismatch_count")) is not int or pixel_audit["label_mismatch_count"] != 0:
        raise ValueError("Independent source-pixel audit found board-label mismatches")
    if pixel_audit.get("colour_counts_match") is not True:
        raise ValueError("Independent source-pixel audit colour counts did not match")
    for key in (
        "source_sha256", "image_size", "grid_size", "pixel_samples_reproduced",
        "extraction_fingerprint_match", "label_mismatch_count", "colour_counts_match",
    ):
        if persisted_audit.get(key) != pixel_audit.get(key):
            raise ValueError(f"Persisted source-pixel audit {key} does not match recomputed audit")

    colour_image_provenance = verify_source_image(board_labels, screenshot_bytes)
    colour_rgb_provenance = _verify_colour_samples(board_labels, board_observation)
    shooter_source_provenance = verify_shooter_source_artifacts(
        shooter_labels, shooter_bytes, screenshot_bytes
    )
    if shooter_labels.get("source_screenshot_sha256") != actual_screenshot_hash:
        raise ValueError("Shooter labels belong to a different screenshot")
    if shooter_labels.get("capture_provenance", {}).get("capture_session_id") != session_id:
        raise ValueError("Shooter label capture session does not match manifest")

    template_baseline_status = _verify_review_template_baselines(
        manifest,
        board_labels,
        shooter_labels,
        board_observation,
        shooter_detection,
        shooter_bytes,
        screenshot_bytes,
    )
    colour_report = evaluate_colour_dataset(board_labels)
    shooter_report = evaluate_shooter_dataset(shooter_labels)

    return {
        "schema_version": 1,
        "evaluator": "evaluate_visual_review_bundle",
        "review_bundle_verified": True,
        "capture_identity": {
            "source_screenshot_sha256": actual_screenshot_hash,
            "source_screenshot_size": screenshot_size,
            "capture_session_id": session_id,
            "captured_at": captured_at,
        },
        "review_artifacts_sha256": {
            "manifest_json": _sha256(manifest_bytes),
            "board_labels_json": _sha256(board_label_bytes),
            "shooter_labels_json": _sha256(shooter_label_bytes),
        },
        "source_artifacts_sha256": {
            **actual_artifact_hashes,
            "source_screenshot": actual_screenshot_hash,
        },
        "source_verification": {
            "manifest_hash_checked": True,
            "source_artifact_hashes_checked": True,
            "board_source_pixels_reproduced": True,
            "board_extraction_fingerprint_matched": True,
            "reviewed_board_rgb_matches_source_observation": True,
            "shooter_detector_snapshot_matched": True,
            **template_baseline_status,
            "screenshot_dimensions_checked": True,
            "board_details": {
                **colour_image_provenance,
                **colour_rgb_provenance,
            },
            "shooter_details": shooter_source_provenance,
        },
        "board_colour_evaluation": colour_report,
        "shooter_observation_evaluation": shooter_report,
        "interpretation": (
            "Board and shooter metrics measure agreement with user-supplied review labels. "
            "The combined report verifies source-artifact identity and that reviewed board RGB "
            "values still match the pinned observation and original screenshot. It does not "
            "independently verify human-label truth, calibration alignment, game colour meaning, "
            "shooter identity, ammunition truth, or gameplay performance."
        ),
        "label_truth_independently_verified": False,
        "calibration_alignment_verified": False,
        "colour_independently_verified": False,
        "ammunition_independently_verified": False,
        "slot_mapping_independently_verified": False,
        "gameplay_verified": False,
        "game_taps_enabled": False,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Evaluate board and shooter reviews bound to one screenshot"
    )
    parser.add_argument("manifest")
    parser.add_argument("board_labels")
    parser.add_argument("shooter_labels")
    parser.add_argument("--board-observation", required=True)
    parser.add_argument("--shooter-detection", required=True)
    parser.add_argument("--pixel-audit", required=True)
    parser.add_argument("--source-screenshot", required=True)
    parser.add_argument("--output", default="data/visual_review_evaluation.json")
    args = parser.parse_args()

    report = evaluate_visual_review_bundle(
        args.manifest,
        args.board_labels,
        args.shooter_labels,
        args.board_observation,
        args.shooter_detection,
        args.pixel_audit,
        args.source_screenshot,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(json.dumps(report, indent=2), encoding="utf-8")
    temporary.replace(output)
    print("SLIME AI — COMBINED VISUAL REVIEW")
    print("=" * 40)
    print("Review bundle verified:", report["review_bundle_verified"])
    print("Board-colour samples:", report["board_colour_evaluation"]["sample_count"])
    print("Board-colour agreement:", report["board_colour_evaluation"]["accuracy"])
    print(
        "Shooter reviewed samples:",
        report["shooter_observation_evaluation"]["confirmed_sample_count"],
    )
    print("Label truth independently verified: False")
    print("Gameplay verified: False")
    print("Game taps enabled: False")
    print("Report:", output)


if __name__ == "__main__":
    main()
