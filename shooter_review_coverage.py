"""Shared descriptive review-coverage helpers for shooter evaluations.

This module counts supplied human-review support. It deliberately avoids
minimum sample thresholds, representativeness claims, and deployment gates.
"""
from collections import Counter

from prepare_shooter_labels import DETECTOR_COLOURS
from shooter_observation_evaluation import HUMAN_VISIBILITY_LABELS


PANEL_POSITION_LABELS = tuple(
    f"r{row}c{column}"
    for row in range(1, 4)
    for column in range(1, 5)
)
SAMPLE_QUALITY_LABELS = (
    "DISTINCT_SAMPLE", "LOW_CONFIDENCE_SAMPLE", "NOT_REPORTED",
)


def coverage_profile(dataset):
    """Describe reviewed support by detector slot and human-labelled class."""
    positions = {
        label: {"confirmed": 0, "ambiguous": 0}
        for label in PANEL_POSITION_LABELS
    }
    visibility = Counter({label: 0 for label in HUMAN_VISIBILITY_LABELS})
    colours = Counter({label: 0 for label in DETECTOR_COLOURS})
    quality = Counter({label: 0 for label in SAMPLE_QUALITY_LABELS})
    ammunition_status = Counter()
    ammunition_values = Counter()

    for sample in dataset["samples"]:
        detector = sample["detector"]
        human = sample["human"]
        position = f"r{detector['row']}c{detector['column']}"
        review_status = sample["review_status"]
        positions[position][review_status] += 1

        if review_status != "confirmed":
            continue

        reviewed_visibility = human["visibility"]
        visibility[reviewed_visibility] += 1
        if reviewed_visibility != "visible":
            continue

        colours[human["colour"]] += 1
        quality[detector.get("sample_quality_status") or "NOT_REPORTED"] += 1
        ammunition_status[
            detector.get("ammunition_observation_status", "NOT_REPORTED")
        ] += 1
        if human["ammunition_readable"] is True:
            ammunition_values[human["ammunition"]] += 1

    return {
        "detector_panel_position_review_counts": positions,
        "human_visibility_class_support": dict(visibility),
        "human_visible_colour_support": dict(colours),
        "human_legible_ammunition_value_support": [
            {"value": value, "count": ammunition_values[value]}
            for value in sorted(ammunition_values)
        ],
        "visible_detector_sample_quality_status_counts": dict(quality),
        "visible_detector_ammunition_ocr_status_counts": dict(
            ammunition_status
        ),
        "panel_positions_with_confirmed_labels": sum(
            counts["confirmed"] > 0 for counts in positions.values()
        ),
        "panel_positions_with_only_ambiguous_labels": sum(
            counts["confirmed"] == 0 and counts["ambiguous"] > 0
            for counts in positions.values()
        ),
        "coverage_adequacy_assessed": False,
    }


def aggregate_coverage_profiles(profiles):
    """Sum per-capture descriptive coverage without converting it to a gate."""
    combined = coverage_profile({"samples": []})
    for profile in profiles:
        for position, counts in profile[
            "detector_panel_position_review_counts"
        ].items():
            for status in ("confirmed", "ambiguous"):
                combined["detector_panel_position_review_counts"][position][status] += (
                    counts[status]
                )
        for field in (
            "human_visibility_class_support",
            "human_visible_colour_support",
            "visible_detector_sample_quality_status_counts",
            "visible_detector_ammunition_ocr_status_counts",
        ):
            target = combined[field]
            for label, count in profile[field].items():
                target[label] = target.get(label, 0) + count
        ammunition_counts = Counter({
            item["value"]: item["count"]
            for item in combined["human_legible_ammunition_value_support"]
        })
        ammunition_counts.update({
            item["value"]: item["count"]
            for item in profile["human_legible_ammunition_value_support"]
        })
        combined["human_legible_ammunition_value_support"] = [
            {"value": value, "count": ammunition_counts[value]}
            for value in sorted(ammunition_counts)
        ]

    positions = combined["detector_panel_position_review_counts"]
    combined["panel_positions_with_confirmed_labels"] = sum(
        counts["confirmed"] > 0 for counts in positions.values()
    )
    combined["panel_positions_with_only_ambiguous_labels"] = sum(
        counts["confirmed"] == 0 and counts["ambiguous"] > 0
        for counts in positions.values()
    )
    return combined


def review_follow_up(profile):
    """Identify observed review gaps without judging dataset adequacy."""
    panel_targets = []
    for position, counts in profile[
        "detector_panel_position_review_counts"
    ].items():
        confirmed = counts["confirmed"]
        ambiguous = counts["ambiguous"]
        if confirmed == 0 and ambiguous == 0:
            status = "not_reviewed"
        elif confirmed == 0:
            status = "ambiguous_only"
        elif ambiguous:
            status = "contains_ambiguous_samples"
        else:
            continue
        panel_targets.append({
            "position": position,
            "status": status,
            "confirmed_count": confirmed,
            "ambiguous_count": ambiguous,
        })

    return {
        "panel_review_targets": panel_targets,
        "visibility_classes_with_zero_confirmed_support": [
            label
            for label, count in profile[
                "human_visibility_class_support"
            ].items()
            if count == 0
        ],
        "visible_colour_classes_with_zero_confirmed_support": [
            label
            for label, count in profile[
                "human_visible_colour_support"
            ].items()
            if count == 0
        ],
        "coverage_adequacy_assessed": False,
        "interpretation": (
            "These are observed gaps in the supplied review set, not required "
            "quotas or a judgement that the dataset is inadequate."
        ),
    }
