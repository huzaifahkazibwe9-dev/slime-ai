
import json
from collections import Counter
from pathlib import Path

from board_loader import load_board
from region_graph import build_region_graph
from reachability_auditor import _audit_core

CALIBRATION_FILE = Path("data/conveyor_calibration.json")
OBSERVATIONS_FILE = Path("data/conveyor_visual_observations.json")
OUTPUT_FILE = Path("data/region_lane_mapping_latest.json")


def map_cell(cell, region_grid, confidence=None):
    row, col = cell.get("row"), cell.get("column")
    h, w = len(region_grid), len(region_grid[0])

    if type(row) is not int or type(col) is not int:
        raise ValueError("Invalid lane-cell coordinates")
    if not (0 <= row < h and 0 <= col < w):
        raise ValueError(f"Lane cell outside board: {(row, col)}")

    result = {
        "row": row,
        "column": col,
        "colour": cell.get("colour"),
        "region_id": region_grid[row][col],
    }
    if confidence is not None:
        result["board_confidence"] = confidence[row][col]
    return result


def map_lane_regions(board, graph, reachability, confidence=None):
    h, w = len(board), len(board[0])
    region_grid = graph.get("cell_region_ids")

    if (
        not isinstance(region_grid, list)
        or len(region_grid) != h
        or any(not isinstance(row, list) or len(row) != w for row in region_grid)
    ):
        raise ValueError("Region coordinate grid is missing or invalid")

    if confidence is not None and (
        len(confidence) != h
        or any(len(row) != w for row in confidence)
    ):
        raise ValueError("Confidence grid dimensions do not match")

    positions = []
    mapped_count = 0

    for position in reachability.get("results", []):
        scenarios = []

        for item in position.get("scenarios", []):
            exposed = [
                map_cell(c, region_grid, confidence)
                for c in item.get("exposed_matching_cells", [])
            ]
            behind = [
                map_cell(c, region_grid, confidence)
                for c in item.get("matching_tiles_behind_blocker", [])
            ]
            lane = [
                map_cell(c, region_grid, confidence)
                for c in item.get("lane_cells", [])
            ]
            blocker = item.get("first_blocker")
            if blocker is not None:
                blocker = map_cell(blocker, region_grid, confidence)

            exposed_counts = Counter(c["region_id"] for c in exposed)
            behind_counts = Counter(c["region_id"] for c in behind)

            mapped_count += len(exposed) + len(behind) + len(lane)
            mapped_count += int(blocker is not None)

            scenarios.append({
                "target_colour": item.get("target_colour"),
                "status": item.get("status"),
                "exposed_matching_count": len(exposed),
                "exposed_cells": exposed,
                "exposed_region_counts": dict(sorted(exposed_counts.items())),
                "exposed_region_ids": sorted(exposed_counts),
                "behind_blocker_count": len(behind),
                "behind_blocker_cells": behind,
                "behind_blocker_region_counts": dict(sorted(behind_counts.items())),
                "behind_blocker_region_ids": sorted(behind_counts),
                "first_blocker": blocker,
                "lane_cells": lane,
            })

        positions.append({
            "position_id": position.get("position_id"),
            "direction": position.get("direction"),
            "first_cell": position.get("first_cell"),
            "observed_colour": position.get("observed_colour"),
            "observed_ammo": position.get("observed_ammo"),
            "identity_verified": False,
            "scenarios": scenarios,
        })

    all_cells_valid = all(
        bool(region_grid[c["row"]][c["column"]])
        for pos in positions
        for scenario in pos["scenarios"]
        for group in (
            scenario["exposed_cells"],
            scenario["behind_blocker_cells"],
            scenario["lane_cells"],
        )
        for c in group
    )

    return {
        "grid_size": [h, w],
        "region_count": graph["region_count"],
        "mapped_positions": len(positions),
        "mapped_cell_references": mapped_count,
        "positions": positions,
        "checks": {
            "region_coordinate_grid_matches_board": True,
            "all_mapped_cells_have_region_ids": all_cells_valid,
        },
        "gameplay_verified": False,
        "shooter_identity_verified": False,
        "colour_mapping_verified": False,
        "planning_authorized": False,
        "game_taps_enabled": False,
        "limitations": [
            "Region mapping does not validate real-game colour classification.",
            "Shooter identities and shooter-to-board colour mappings remain unverified.",
            "Lane reachability is based on the existing read-only geometric audit.",
            "Boundary cells require confirmation; interior cells remain provisional.",
        ],
    }


def audit_files():
    loaded = load_board()
    board = loaded["board"]
    calibration = json.loads(CALIBRATION_FILE.read_text())
    observations = json.loads(OBSERVATIONS_FILE.read_text())

    graph = build_region_graph(board)
    reachability = _audit_core(
        {"board": board}, calibration, observations
    )
    report = map_lane_regions(
        board, graph, reachability, confidence=loaded["confidence"]
    )

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(json.dumps(report, indent=2))

    print("SLIME AI — BUILD 11AA REGION/LANE MAPPER")
    print("=" * 48)
    print("Grid:", report["grid_size"])
    print("Regions:", report["region_count"])
    print("Shooter positions:", report["mapped_positions"])
    print("Mapped cell references:", report["mapped_cell_references"])

    for position in report["positions"]:
        print("\n", position["position_id"], position["direction"])
        for scenario in position["scenarios"]:
            print(
                " ", scenario["target_colour"],
                "exposed=", scenario["exposed_matching_count"],
                "regions=", scenario["exposed_region_counts"],
                "behind=", scenario["behind_blocker_region_counts"],
            )

    for name, passed in report["checks"].items():
        print(f"[{'PASS' if passed else 'FAIL'}] {name}")

    print("Gameplay verified:", report["gameplay_verified"])
    print("Planning authorized:", report["planning_authorized"])
    print("Game taps enabled:", report["game_taps_enabled"])
    print("Report:", OUTPUT_FILE)

    if not all(report["checks"].values()):
        raise SystemExit("Build11AA checks failed")
    return report


if __name__ == "__main__":
    audit_files()
