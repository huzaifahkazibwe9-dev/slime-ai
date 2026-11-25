#!/usr/bin/env python3

import json
from strict_json import strict_json_loads
from collections import defaultdict, deque
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "data" / "vision_level39.json"
OUTPUT = ROOT / "data" / "color_components.json"

DIRECTIONS = (
    (-1, 0),
    (1, 0),
    (0, -1),
    (0, 1),
)


def load_board():
    if not SOURCE.exists():
        raise FileNotFoundError(SOURCE)

    data = strict_json_loads(SOURCE.read_text())
    board = data.get("board")

    if not isinstance(board, list) or len(board) != 35:
        raise ValueError("Expected exactly 35 board rows.")

    for row in board:
        if not isinstance(row, list) or len(row) != 35:
            raise ValueError("Expected exactly 35 cells per row.")

    total = sum(len(row) for row in board)

    if total != 1225:
        raise ValueError(f"Expected 1225 cells, found {total}.")

    return data, board


def find_components(board):
    height = len(board)
    width = len(board[0])

    visited = [[False] * width for _ in range(height)]
    components = defaultdict(list)

    for start_r in range(height):
        for start_c in range(width):
            if visited[start_r][start_c]:
                continue

            colour = board[start_r][start_c]
            queue = deque([(start_r, start_c)])
            visited[start_r][start_c] = True
            cells = []

            while queue:
                r, c = queue.popleft()
                cells.append([r, c])

                for dr, dc in DIRECTIONS:
                    nr, nc = r + dr, c + dc

                    if not (0 <= nr < height and 0 <= nc < width):
                        continue

                    if visited[nr][nc]:
                        continue

                    if board[nr][nc] != colour:
                        continue

                    visited[nr][nc] = True
                    queue.append((nr, nc))

            rows = [cell[0] for cell in cells]
            cols = [cell[1] for cell in cells]

            components[colour].append({
                "size": len(cells),
                "bounds": [
                    min(rows), min(cols),
                    max(rows), max(cols)
                ],
                "touches_board_edge": any(
                    r == 0 or c == 0
                    or r == height - 1 or c == width - 1
                    for r, c in cells
                ),
                "sample_cells": cells[:8],
            })

    for colour in components:
        components[colour].sort(
            key=lambda item: item["size"],
            reverse=True
        )

    return dict(components)


def run_tests():
    # Diagonal cells must remain separate with 4-directional connectivity.
    diagonal = [
        ["red", "blue"],
        ["blue", "red"],
    ]

    result = find_components(diagonal)

    assert len(result["red"]) == 2
    assert len(result["blue"]) == 2
    assert all(item["size"] == 1 for group in result.values()
               for item in group)

    # Orthogonally adjacent cells must form one component.
    adjacent = [
        ["red", "red"],
        ["blue", "red"],
    ]

    result = find_components(adjacent)

    assert len(result["red"]) == 1
    assert result["red"][0]["size"] == 3
    assert len(result["blue"]) == 1

    print("[PASS] Diagonal separation")
    print("[PASS] Orthogonal connection")
    print("Component tests: 2/2 passed")


def main():
    run_tests()

    data, board = load_board()
    components = find_components(board)

    colour_counts = defaultdict(int)

    for row in board:
        for colour in row:
            colour_counts[colour] += 1

    result = {
        "version": 1,
        "source": "vision_level39.json",
        "grid_size": [35, 35],
        "connectivity": "four_directional",
        "source_cells": 1225,
        "occupancy_mask_used": False,
        "gameplay_verified": False,
        "colour_counts": dict(sorted(colour_counts.items())),
        "component_counts": {
            colour: len(items)
            for colour, items in sorted(components.items())
        },
        "components": components,
    }

    OUTPUT.write_text(json.dumps(result, indent=2))

    print("\nSLIME AI — COLOUR COMPONENT AUDIT")
    print("=" * 45)
    print("Board: 35 x 35")
    print("Cells analysed:", sum(colour_counts.values()))
    print("Connectivity: 4-directional")
    print("Legacy occupancy mask used: NO")
    print("Gameplay verified: NO")

    for colour in sorted(components):
        items = components[colour]
        print(f"\n{colour}: {colour_counts[colour]} cells")
        print("Connected components:", len(items))

        for index, item in enumerate(items[:10], 1):
            print(
                f"  {index}. size={item['size']} "
                f"bounds={item['bounds']} "
                f"edge={item['touches_board_edge']}"
            )

        if len(items) > 10:
            print(f"  ... {len(items) - 10} more components")

    print("\nSaved:", OUTPUT)
    print("Original board data was not modified.")
    print("No gameplay actions were performed.")


if __name__ == "__main__":
    main()
