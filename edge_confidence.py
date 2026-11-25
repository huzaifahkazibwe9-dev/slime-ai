import hashlib
import json
from pathlib import Path

def analyze_board(board):
    if not isinstance(board, list) or not board:
        raise ValueError("Board must be a non-empty list")

    if not all(isinstance(row, list) and row for row in board):
        raise ValueError("Every board row must be a non-empty list")

    width = len(board[0])
    if any(len(row) != width for row in board):
        raise ValueError("Board must be rectangular")

    height = len(board)
    cells = []
    boundary_count = 0
    interior_count = 0

    for r, row in enumerate(board):
        output_row = []
        for c, colour in enumerate(row):
            boundary = (
                r == 0 or r == height - 1
                or c == 0 or c == width - 1
            )

            if boundary:
                confidence = "requires_confirmation"
                boundary_count += 1
            else:
                confidence = "provisional"
                interior_count += 1

            output_row.append({
                "row": r,
                "column": c,
                "colour": colour,
                "is_boundary": boundary,
                "confidence": confidence
            })
        cells.append(output_row)

    return {
        "grid_size": [height, width],
        "total_cells": height * width,
        "boundary_cells": boundary_count,
        "interior_cells": interior_count,
        "cells": cells,
        "all_cells_preserved": True,
        "tile_removals_verified": False,
        "board_transition_verified": False,
        "game_taps_enabled": False
    }


def analyze_snapshot(source_bytes, source_path):
    """Build edge-confidence metadata from the exact parsed board bytes."""
    data = json.loads(source_bytes)
    if not isinstance(data, dict):
        raise ValueError("Board source must be a JSON object")
    report = analyze_board(data.get("board"))
    report["source"] = str(source_path)
    report["source_grid_size"] = data.get("grid_size")
    report["source_file_sha256"] = {
        "vision_level39_json": hashlib.sha256(source_bytes).hexdigest()
    }
    return report


def main():
    source = Path("data/vision_level39.json")
    destination = Path("data/edge_confidence_latest.json")

    if not source.exists():
        raise FileNotFoundError(f"Missing input: {source}")

    source_bytes = source.read_bytes()
    report = analyze_snapshot(source_bytes, source)

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2))

    print("\nBUILD 11E — EDGE CONFIDENCE")
    print("=" * 48)
    print(f"Grid: {report['grid_size'][0]} x {report['grid_size'][1]}")
    print(f"Total cells preserved: {report['total_cells']}")
    print(f"Boundary cells needing confirmation: {report['boundary_cells']}")
    print(f"Interior provisional cells: {report['interior_cells']}")
    print(f"Report: {destination}")
    print(f"All cells preserved: {report['all_cells_preserved']}")
    print(f"Tile removals verified: {report['tile_removals_verified']}")
    print(f"Board transition verified: {report['board_transition_verified']}")
    print(f"Gameplay taps enabled: {report['game_taps_enabled']}")


if __name__ == "__main__":
    main()
