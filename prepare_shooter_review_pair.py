#!/usr/bin/env python3
"""Create two blank, source-bound reviewer templates and a paired manifest."""
import argparse
import copy
import json
import os
import re
from pathlib import Path

from prepare_shooter_labels import build_template
from strict_json import strict_json_loads


def _reviewer_slug(value, name):
    if not isinstance(value, str) or not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9_-]{0,39}", value
    ):
        raise ValueError(
            f"{name} must be 1-40 letters, digits, underscores, or hyphens"
        )
    return value


def _atomic_json(path, value):
    temporary = path.with_name(path.name + ".tmp")
    try:
        temporary.write_text(
            json.dumps(value, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def prepare_review_pair(
    detection_path,
    screenshot_path,
    output_dir,
    reviewer_a_id="reviewer-a",
    reviewer_b_id="reviewer-b",
    overwrite=False,
):
    """Write two separate blank templates bound to the exact same capture."""
    reviewer_a_id = _reviewer_slug(reviewer_a_id, "reviewer_a_id")
    reviewer_b_id = _reviewer_slug(reviewer_b_id, "reviewer_b_id")
    if reviewer_a_id.casefold() == reviewer_b_id.casefold():
        raise ValueError("Reviewer identifiers must be distinct")

    detection_path = Path(detection_path).expanduser().resolve()
    screenshot_path = Path(screenshot_path).expanduser().resolve()
    output_dir = Path(output_dir).expanduser().resolve()
    try:
        detection_bytes = detection_path.read_bytes()
        screenshot_bytes = screenshot_path.read_bytes()
        detection = strict_json_loads(detection_bytes)
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise ValueError(f"Unable to read source capture artifacts: {exc}") from exc

    template = build_template(detection, detection_bytes, screenshot_bytes)
    if template.get("labelled_by_user") is not False:
        raise ValueError("New review templates must start unlabelled")

    output_dir.mkdir(parents=True, exist_ok=True)
    dataset_a_path = output_dir / f"{reviewer_a_id}.json"
    dataset_b_path = output_dir / f"{reviewer_b_id}.json"
    manifest_path = output_dir / "review_manifest.json"
    targets = (dataset_a_path, dataset_b_path, manifest_path)
    existing = [path for path in targets if path.exists()]
    if existing and not overwrite:
        names = ", ".join(path.name for path in existing)
        raise FileExistsError(
            f"Refusing to overwrite existing review files: {names}; pass overwrite=True to replace"
        )

    # The two JSON files are serialized from detached copies so subsequent
    # edits to one review cannot affect the other.
    dataset_a = copy.deepcopy(template)
    dataset_b = copy.deepcopy(template)
    manifest = {
        "schema_version": 1,
        "captures": [{
            "reviewer_a_dataset": dataset_a_path.name,
            "reviewer_b_dataset": dataset_b_path.name,
            "detection": os.path.relpath(detection_path, output_dir),
            "screenshot": os.path.relpath(screenshot_path, output_dir),
        }],
    }

    written = []
    try:
        _atomic_json(dataset_a_path, dataset_a)
        written.append(dataset_a_path)
        _atomic_json(dataset_b_path, dataset_b)
        written.append(dataset_b_path)
        _atomic_json(manifest_path, manifest)
        written.append(manifest_path)
    except OSError:
        if not overwrite:
            for path in written:
                path.unlink(missing_ok=True)
        raise

    return {
        "reviewer_a_dataset": dataset_a_path,
        "reviewer_b_dataset": dataset_b_path,
        "manifest": manifest_path,
        "source_detection_sha256": template["source_detection_sha256"],
        "source_screenshot_sha256": template["source_screenshot_sha256"],
        "sample_count": len(template["samples"]),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Create two independent blank shooter-review templates"
    )
    parser.add_argument("detection", help="Exact detector JSON for the screenshot")
    parser.add_argument("screenshot", help="Original screenshot used by the detector")
    parser.add_argument("--output-dir", default="data/review-pair")
    parser.add_argument("--reviewer-a-id", default="reviewer-a")
    parser.add_argument("--reviewer-b-id", default="reviewer-b")
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace existing templates and manifest in the output directory",
    )
    args = parser.parse_args()

    try:
        result = prepare_review_pair(
            args.detection,
            args.screenshot,
            args.output_dir,
            args.reviewer_a_id,
            args.reviewer_b_id,
            args.overwrite,
        )
    except (ValueError, FileExistsError, OSError) as exc:
        parser.error(str(exc))

    print("SLIME AI — PAIRED REVIEW TEMPLATES")
    print("Reviewer A template:", result["reviewer_a_dataset"])
    print("Reviewer B template:", result["reviewer_b_dataset"])
    print("Agreement manifest:", result["manifest"])
    print("Blank samples per reviewer:", result["sample_count"])
    print("Shared detector SHA-256:", result["source_detection_sha256"])
    print("Shared screenshot SHA-256:", result["source_screenshot_sha256"])
    print("Human labels prefilled: False")
    print("Reviewer independence verified: False")
    print("Gameplay verified: False")
    print("Game taps enabled: False")


if __name__ == "__main__":
    main()
