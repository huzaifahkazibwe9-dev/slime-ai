import json
from strict_json import strict_json_loads
from collections import deque, Counter
from pathlib import Path


def analyze_board(board):
    if not isinstance(board, list) or not board:
        raise ValueError("Board must be a non-empty list.")
    width = len(board[0])
    if width == 0 or any(not isinstance(row, list) or len(row) != width for row in board):
        raise ValueError("Board must be rectangular.")
    if any(not isinstance(colour, str) or not colour for row in board for colour in row):
        raise ValueError("Every board cell must contain a colour label.")

    height = len(board)
    visited = set()
    components = []
    colour_counts = Counter(cell for row in board for cell in row)

    for r in range(height):
        for c in range(width):
            if (r, c) in visited:
                continue

            colour = board[r][c]
            queue = deque([(r, c)])
            visited.add((r, c))
            cells = []

            while queue:
                cr, cc = queue.popleft()
                cells.append((cr, cc))

                for nr, nc in (
                    (cr - 1, cc), (cr + 1, cc),
                    (cr, cc - 1), (cr, cc + 1)
                ):
                    if (
                        0 <= nr < height
                        and 0 <= nc < width
                        and (nr, nc) not in visited
                        and board[nr][nc] == colour
                    ):
                        visited.add((nr, nc))
                        queue.append((nr, nc))

            rows = [p[0] for p in cells]
            cols = [p[1] for p in cells]
            edge_count = sum(
                rr in (0, height - 1) or cc in (0, width - 1)
                for rr, cc in cells
            )

            components.append({
                "id": f"{colour}_{len([x for x in components if x['colour'] == colour]) + 1}",
                "colour": colour,
                "size": len(cells),
                "bounds": [min(rows), min(cols), max(rows), max(cols)],
                "row_span": max(rows) - min(rows) + 1,
                "column_span": max(cols) - min(cols) + 1,
                "edge_cells": edge_count,
                "edge_contact": edge_count > 0,
            })

    components.sort(key=lambda item: (-item["size"], item["colour"], item["id"]))

    component_counts = Counter(item["colour"] for item in components)
    reconstructed_counts = Counter()
    for item in components:
        reconstructed_counts[item["colour"]] += item["size"]

    return {
        "grid_size": [height, width],
        "total_cells": height * width,
        "colour_counts": dict(sorted(colour_counts.items())),
        "component_counts": dict(sorted(component_counts.items())),
        "components": components,
        "checks": {
            "all_cells_accounted_for": sum(x["size"] for x in components) == height * width,
            "colour_counts_reconstructed": dict(reconstructed_counts) == dict(colour_counts),
            "four_directional_connectivity": True,
        },
        "gameplay_verified": False,
        "pixel_removal_verified": False,
        "game_taps_enabled": False,
    }


def audit_file(source_path="data/vision_level39.json",
               output_path="data/color_topology_latest.json"):
    source = strict_json_loads(Path(source_path).read_text())
    report = analyze_board(source["board"])

    saved_counts = source.get("counts", {})
    report["checks"]["source_colour_counts_match"] = (
        dict(sorted(saved_counts.items())) == report["colour_counts"]
    )

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2))

    print("SLIME AI — COLOUR TOPOLOGY AUDIT")
    print("=" * 48)
    print("Grid:", report["grid_size"])
    print("Cells:", report["total_cells"])
    print("Colour regions:", len(report["components"]))
    print("\nCOLOUR SUMMARY")

    for colour, count in report["colour_counts"].items():
        print(
            f"{colour:10} tiles={count:4} "
            f"regions={report['component_counts'][colour]:3}"
        )

    print("\nLARGEST REGIONS")
    for item in report["components"][:12]:
        print(
            f"{item['id']:14} size={item['size']:4} "
            f"bounds={item['bounds']} "
            f"edge_cells={item['edge_cells']}"
        )

    print("\nCHECKS")
    for name, passed in report["checks"].items():
        print(f"[{'PASS' if passed else 'FAIL'}] {name}")

    print("\nGameplay verified:", report["gameplay_verified"])
    print("Game taps enabled:", report["game_taps_enabled"])
    print("Report:", output_path)

    if not all(report["checks"].values()):
        raise SystemExit("Colour topology audit failed.")

    return report


if __name__ == "__main__":
    audit_file()
