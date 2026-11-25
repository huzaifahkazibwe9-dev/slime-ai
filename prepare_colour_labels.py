#!/usr/bin/env python3
"""Create a human-labelling template from a screenshot-ingestion observation.

The generated template is intentionally NOT evaluable until a person reviews
the source screenshot, fills every label, and changes labelled_by_user to true.
Predicted board colours are never copied into the label field.
"""
import argparse
import json
from pathlib import Path


def build_template(observation):
    if not isinstance(observation, dict):
        raise ValueError("Observation must be a JSON object")

    image_size = observation.get("image_size")
    if (not isinstance(image_size, list) or len(image_size) != 2
            or any(type(value) is not int or value < 1 for value in image_size)):
        raise ValueError("image_size must contain positive integer width and height")

    raw_rgb = observation.get("raw_rgb")
    grid_size = observation.get("grid_size")
    if (not isinstance(grid_size, list) or len(grid_size) != 2
            or any(type(value) is not int or value < 1 for value in grid_size)):
        raise ValueError("grid_size must contain positive integer columns and rows")
    cols, rows = grid_size

    if not isinstance(raw_rgb, list) or len(raw_rgb) != rows:
        raise ValueError("raw_rgb row count does not match grid_size")
    if any(not isinstance(row, list) or len(row) != cols for row in raw_rgb):
        raise ValueError("raw_rgb column count does not match grid_size")

    source_hash = observation.get("source_sha256")
    if (not isinstance(source_hash, str) or len(source_hash) != 64
            or any(char not in "0123456789abcdef" for char in source_hash.lower())):
        raise ValueError("source_sha256 must be a 64-character hexadecimal digest")

    samples = []
    for row_index, row in enumerate(raw_rgb):
        for col_index, rgb in enumerate(row):
            if (not isinstance(rgb, list) or len(rgb) != 3
                    or any(type(channel) is not int or not 0 <= channel <= 255
                           for channel in rgb)):
                raise ValueError(
                    f"raw_rgb[{row_index}][{col_index}] must be three integers in [0, 255]"
                )
            samples.append({
                "id": f"r{row_index + 1:02d}c{col_index + 1:02d}",
                "row": row_index,
                "column": col_index,
                "rgb": rgb[:],
                "label": "",
            })

    return {
        "schema_version": 1,
        "labelled_by_user": False,
        "source_sha256": source_hash.lower(),
        "image_size": image_size[:],
        "grid_size": grid_size[:],
        "samples": samples,
        "labelling_instructions": (
            "Review the original screenshot and fill each label manually. "
            "Do not copy the predicted board labels. After reviewing every sample, "
            "set labelled_by_user to true before running vision_calibration.py."
        ),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Prepare an unlabelled RGB template for manual board-colour review"
    )
    parser.add_argument("observation", help="JSON output from screenshot_ingestor.py")
    parser.add_argument("--output", default="data/colour_labels_template.json")
    args = parser.parse_args()

    observation = json.loads(Path(args.observation).read_text(encoding="utf-8"))
    template = build_template(observation)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(json.dumps(template, indent=2), encoding="utf-8")
    temporary.replace(output)

    print("SLIME AI — HUMAN COLOUR LABEL TEMPLATE")
    print("=" * 44)
    print("Samples prepared:", len(template["samples"]))
    print("Source SHA256:", template["source_sha256"])
    print("User labels supplied: False")
    print("Evaluation-ready: False")
    print("Template:", output)


if __name__ == "__main__":
    main()
