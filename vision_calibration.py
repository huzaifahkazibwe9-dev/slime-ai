#!/usr/bin/env python3
"""Evaluate board-colour classification against explicitly user-labelled RGB samples.

Dataset format:
{
  "schema_version": 1,
  "labelled_by_user": true,
  "samples": [{"id": "sample-1", "rgb": [12, 180, 220], "label": "cyan"}]
}

This measures agreement with the supplied labels. It does not independently
establish that labels are correct or that the samples represent gameplay.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path

from screenshot_ingestor import COLOUR_LABELS, classify_rgb

SCHEMA_VERSION = 1


def validate_dataset(data):
    if not isinstance(data, dict):
        raise ValueError("Dataset must be a JSON object")
    if type(data.get("schema_version")) is not int or data["schema_version"] != SCHEMA_VERSION:
        raise ValueError(f"schema_version must be {SCHEMA_VERSION}")
    if data.get("labelled_by_user") is not True:
        raise ValueError("Dataset must explicitly set labelled_by_user to true")

    source_sha256 = data.get("source_sha256")
    if source_sha256 is not None and (
        not isinstance(source_sha256, str)
        or re.fullmatch(r"[0-9a-f]{64}", source_sha256) is None
    ):
        raise ValueError("source_sha256 must be a lowercase 64-character hexadecimal digest")

    image_size = data.get("image_size")
    grid_size = data.get("grid_size")
    if (image_size is None) != (grid_size is None):
        raise ValueError("image_size and grid_size must be supplied together")
    if image_size is not None:
        if (not isinstance(image_size, list) or len(image_size) != 2
                or any(type(value) is not int or value < 1 for value in image_size)):
            raise ValueError("image_size must contain positive integer width and height")
        if (not isinstance(grid_size, list) or len(grid_size) != 2
                or any(type(value) is not int or value < 1 for value in grid_size)):
            raise ValueError("grid_size must contain positive integer columns and rows")

    samples = data.get("samples")
    if not isinstance(samples, list) or not samples:
        raise ValueError("samples must be a non-empty list")

    seen_ids = set()
    validated = []
    for index, sample in enumerate(samples):
        if not isinstance(sample, dict):
            raise ValueError(f"Sample {index} must be an object")
        sample_id = sample.get("id")
        if not isinstance(sample_id, str) or not sample_id.strip():
            raise ValueError(f"Sample {index} must have a non-empty string id")
        if sample_id in seen_ids:
            raise ValueError(f"Duplicate sample id: {sample_id}")
        seen_ids.add(sample_id)

        rgb = sample.get("rgb")
        if (not isinstance(rgb, list) or len(rgb) != 3
                or any(type(channel) is not int or not 0 <= channel <= 255
                       for channel in rgb)):
            raise ValueError(f"Sample {sample_id} rgb must be three integers in [0, 255]")
        if image_size is not None:
            row = sample.get("row")
            column = sample.get("column")
            if (type(row) is not int or type(column) is not int
                    or not 0 <= row < grid_size[1]
                    or not 0 <= column < grid_size[0]):
                raise ValueError(
                    f"Sample {sample_id} row/column must be valid zero-based grid coordinates"
                )
        label = sample.get("label")
        if not isinstance(label, str) or not label.strip():
            raise ValueError(f"Sample {sample_id} label must be a non-empty string")
        label = label.strip()
        if label not in COLOUR_LABELS:
            allowed = ", ".join(COLOUR_LABELS)
            raise ValueError(f"Sample {sample_id} label must be one of: {allowed}")
        validated_sample = {"id": sample_id, "rgb": rgb[:], "label": label}
        if image_size is not None:
            validated_sample["row"] = row
            validated_sample["column"] = column
        validated.append(validated_sample)
    return validated


def summarize_coverage(samples, data):
    """Summarize observed class and board-quadrant coverage; never infer adequacy."""
    class_counts = {label: 0 for label in COLOUR_LABELS}
    for sample in samples:
        class_counts[sample["label"]] += 1

    has_grid = data.get("grid_size") is not None
    result = {
        "class_sample_counts": class_counts,
        "missing_classes": [label for label, count in class_counts.items() if count == 0],
        "spatial_coverage_available": has_grid,
        "spatial_regions": None,
        "coverage_adequacy_assessed": False,
    }
    if not has_grid:
        return result

    columns, rows = data["grid_size"]
    regions = {
        "top_left": [], "top_right": [],
        "bottom_left": [], "bottom_right": [],
    }
    for sample in samples:
        vertical = "top" if sample["row"] < rows / 2 else "bottom"
        horizontal = "left" if sample["column"] < columns / 2 else "right"
        regions[f"{vertical}_{horizontal}"].append(sample["label"])

    result["spatial_regions"] = {
        name: {
            "sample_count": len(region_labels),
            "class_sample_counts": {
                label: region_labels.count(label) for label in COLOUR_LABELS
            },
        }
        for name, region_labels in regions.items()
    }
    result["empty_spatial_regions"] = [
        name for name, region in result["spatial_regions"].items()
        if region["sample_count"] == 0
    ]
    return result


def evaluate_dataset(data):
    samples = validate_dataset(data)
    evaluated = []
    labels = set()
    for sample in samples:
        predicted = classify_rgb(tuple(sample["rgb"]))
        actual = sample["label"]
        labels.add(actual)
        labels.add(predicted)
        evaluated.append({
            "id": sample["id"],
            "actual": actual,
            "predicted": predicted,
            "correct": actual == predicted,
        })

    ordered_labels = sorted(labels)
    confusion = {
        actual: {
            predicted: sum(
                item["actual"] == actual and item["predicted"] == predicted
                for item in evaluated
            )
            for predicted in ordered_labels
        }
        for actual in ordered_labels
    }

    per_class = {}
    recalls = []
    for label in ordered_labels:
        true_positive = confusion[label][label]
        support = sum(confusion[label].values())
        predicted_count = sum(confusion[actual][label] for actual in ordered_labels)
        precision = true_positive / predicted_count if predicted_count else 0.0
        recall = true_positive / support if support else 0.0
        f1 = (
            2 * precision * recall / (precision + recall)
            if precision + recall else 0.0
        )
        per_class[label] = {
            "support": support,
            "predicted_count": predicted_count,
            "precision": round(precision, 6),
            "recall": round(recall, 6),
            "f1": round(f1, 6),
        }
        if support:
            recalls.append(recall)

    correct = sum(item["correct"] for item in evaluated)
    total = len(evaluated)
    return {
        "schema_version": SCHEMA_VERSION,
        "classifier": "screenshot_ingestor.classify_rgb",
        "sample_count": total,
        "coverage": summarize_coverage(samples, data),
        "source_provenance": {
            "source_sha256": data.get("source_sha256"),
            "image_size": data.get("image_size"),
            "grid_size": data.get("grid_size"),
            "source_image_hash_checked": False,
        },
        "correct_count": correct,
        "accuracy": round(correct / total, 6),
        "macro_recall": round(sum(recalls) / len(recalls), 6) if recalls else 0.0,
        "labels": ordered_labels,
        "confusion_matrix": confusion,
        "per_class": per_class,
        "sample_results": evaluated,
        "label_source": "user_supplied",
        "label_truth_independently_verified": False,
        "gameplay_verified": False,
        "game_taps_enabled": False,
        "interpretation": (
            "Metrics measure agreement with the supplied user-labelled samples. "
            "They do not independently verify label correctness, dataset coverage, "
            "gameplay colour mapping, or real-world gameplay performance."
        ),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Evaluate Slime AI board-colour classification on user-labelled RGB samples"
    )
    parser.add_argument("dataset", help="JSON file containing user-labelled RGB samples")
    parser.add_argument("--output", default="data/colour_evaluation_report.json")
    parser.add_argument(
        "--source-image",
        help="Original screenshot; when supplied, its SHA-256 must match the template",
    )
    args = parser.parse_args()

    data = json.loads(Path(args.dataset).read_text(encoding="utf-8"))
    report = evaluate_dataset(data)
    if args.source_image:
        expected = data.get("source_sha256")
        if not isinstance(expected, str):
            raise ValueError("Dataset has no source_sha256; cannot verify --source-image")
        actual = hashlib.sha256(Path(args.source_image).read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError("Source screenshot SHA-256 does not match the labelled dataset")
        report["source_provenance"]["source_image_hash_checked"] = True
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(json.dumps(report, indent=2), encoding="utf-8")
    temporary.replace(output)

    print("SLIME AI — LABELLED COLOUR EVALUATION")
    print("=" * 44)
    print("Samples:", report["sample_count"])
    print("Accuracy:", report["accuracy"])
    print("Macro recall:", report["macro_recall"])
    print("Labels:", ", ".join(report["labels"]))
    print("Independent label verification: False")
    print("Gameplay verified: False")
    print("Game taps enabled: False")
    print("Report:", output)


if __name__ == "__main__":
    main()
