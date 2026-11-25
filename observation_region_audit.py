#!/usr/bin/env python3
"""Build a provisional colour-region graph from the latest screenshot observation."""
import argparse
import json
from strict_json import strict_json_loads
from pathlib import Path

from color_topology import analyze_board
from screenshot_observation_loader import _require_grid

DEFAULT_INPUT = Path("data/board_observation_latest.json")
DEFAULT_OUTPUT = Path("data/observation_regions_latest.json")


def audit_observation(data):
    width, height, board, counts = _require_grid(data)
    graph = analyze_board(board)

    if graph["total_cells"] != width * height:
        raise ValueError("Region graph cell count does not match observation")
    if graph["colour_counts"] != dict(counts):
        raise ValueError("Region graph colour counts do not match observation")
    if not all(graph["checks"].values()):
        raise ValueError("Region graph integrity checks failed")

    return {
        "source": "screenshot_observation",
        "snapshot_id": data["snapshot_id"],
        "grid_size": [width, height],
        "total_cells": graph["total_cells"],
        "region_count": len(graph["components"]),
        "colour_counts": graph["colour_counts"],
        "component_counts": graph["component_counts"],
        "largest_regions": graph["components"][:20],
        "integrity_checks": graph["checks"],
        "classifier_consistent_with_saved_rgb": True,
        "colour_truth_verified": False,
        "shooter_mapping_verified": False,
        "planning_authorized": False,
        "gameplay_verified": False,
        "game_taps_enabled": False,
        "interpretation": (
            "Regions are derived from provisional screenshot colour labels. "
            "They are useful for structural analysis only; they do not prove "
            "the real game's tile colours or shooter-to-board mappings."
        ),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Audit provisional colour regions in a screenshot observation"
    )
    parser.add_argument("--input", default=str(DEFAULT_INPUT))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    data = strict_json_loads(Path(args.input).read_text())
    report = audit_observation(data)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(json.dumps(report, indent=2))
    temporary.replace(output)

    print("SLIME AI — SCREENSHOT COLOUR REGION AUDIT")
    print("=" * 50)
    print("Snapshot:", report["snapshot_id"])
    print("Grid:", report["grid_size"])
    print("Cells:", report["total_cells"])
    print("Regions:", report["region_count"])
    print("Colour counts:", report["colour_counts"])
    print("\nLARGEST REGIONS")
    for item in report["largest_regions"][:12]:
        print(
            item["id"], "|", item["colour"],
            "| size:", item["size"],
            "| bounds:", item["bounds"],
        )
    print("\nIntegrity checks:", report["integrity_checks"])
    print("Colour truth verified: False")
    print("Planning authorized: False")
    print("Game taps enabled: False")
    print("Report:", output)


if __name__ == "__main__":
    main()
