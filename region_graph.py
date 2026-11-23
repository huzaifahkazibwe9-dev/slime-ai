import json
from collections import deque, Counter
from pathlib import Path


def build_region_graph(board):
    if not isinstance(board, list) or not board:
        raise ValueError("Board must be non-empty.")

    h = len(board)
    if not isinstance(board[0], list) or not board[0]:
        raise ValueError("Board rows must be non-empty.")

    w = len(board[0])
    if any(not isinstance(row, list) or len(row) != w for row in board):
        raise ValueError("Board must be rectangular.")
    if any(v is not None and (not isinstance(v, str) or not v) for row in board for v in row):
        raise ValueError("Every cell must have a colour label.")

    labels = [[None] * w for _ in range(h)]
    regions = {}
    next_id = 0

    for r in range(h):
        for c in range(w):
            if labels[r][c] is not None:
                continue

            colour = board[r][c]
            if colour is None:
                continue
            region_id = f"R{next_id:03d}"
            next_id += 1
            queue = deque([(r, c)])
            labels[r][c] = region_id
            cells = []
            min_r = max_r = r
            min_c = max_c = c

            while queue:
                cr, cc = queue.popleft()
                cells.append((cr, cc))
                min_r = min(min_r, cr)
                max_r = max(max_r, cr)
                min_c = min(min_c, cc)
                max_c = max(max_c, cc)

                for nr, nc in (
                    (cr - 1, cc), (cr + 1, cc),
                    (cr, cc - 1), (cr, cc + 1)
                ):
                    if (
                        0 <= nr < h and 0 <= nc < w
                        and labels[nr][nc] is None
                        and board[nr][nc] == colour
                    ):
                        labels[nr][nc] = region_id
                        queue.append((nr, nc))

            perimeter = 0
            boundary_cells = set()
            for cr, cc in cells:
                for nr, nc in (
                    (cr - 1, cc), (cr + 1, cc),
                    (cr, cc - 1), (cr, cc + 1)
                ):
                    if not (0 <= nr < h and 0 <= nc < w):
                        perimeter += 1
                        boundary_cells.add((cr, cc))
                    elif board[nr][nc] != colour:
                        perimeter += 1
                        boundary_cells.add((cr, cc))

            regions[region_id] = {
                "id": region_id,
                "colour": colour,
                "size": len(cells),
                "bounds": [
                    min_r,
                    min_c,
                    max_r,
                    max_c,
                ],
                "perimeter": perimeter,
                "boundary_cells": len(boundary_cells),
                "neighbors": {},
            }

    shared = Counter()
    for r in range(h):
        for c in range(w):
            here = labels[r][c]
            for nr, nc in ((r + 1, c), (r, c + 1)):
                if nr < h and nc < w:
                    other = labels[nr][nc]
                    if here is not None and other is not None and here != other:
                        pair = tuple(sorted((here, other)))
                        shared[pair] += 1

    for (a, b), edges in shared.items():
        regions[a]["neighbors"][b] = edges
        regions[b]["neighbors"][a] = edges

    region_list = list(regions.values())
    region_list.sort(key=lambda x: (-x["size"], x["id"]))

    for region in region_list:
        region["neighbor_count"] = len(region["neighbors"])
        region["neighbor_ids"] = sorted(region["neighbors"])

    total_shared = sum(shared.values())
    return {
        "grid_size": [h, w],
        "cell_region_ids": labels,
        "total_cells": h * w,
        "occupied_cells": sum(v is not None for row in board for v in row),
        "empty_cells": sum(v is None for row in board for v in row),
        "region_count": len(regions),
        "regions": region_list,
        "adjacency_edges": [
            {"region_a": a, "region_b": b, "shared_border": n}
            for (a, b), n in sorted(shared.items())
        ],
        "total_shared_border_edges": total_shared,
        "checks": {
            "all_occupied_cells_assigned": all(
                (board[r][c] is None and labels[r][c] is None)
                or (board[r][c] is not None and labels[r][c] is not None)
                for r in range(h) for c in range(w)
            ),
            "all_regions_nonempty": all(x["size"] > 0 for x in region_list),
            "adjacency_is_symmetric": all(
                regions[a]["neighbors"].get(b) == n
                and regions[b]["neighbors"].get(a) == n
                for (a, b), n in shared.items()
            ),
            "region_sizes_sum_to_board": sum(
                x["size"] for x in region_list
            ) == sum(v is not None for row in board for v in row),
        },
        "gameplay_verified": False,
        "game_taps_enabled": False,
    }


def audit_file():
    source = json.loads(Path("data/vision_level39.json").read_text())
    report = build_region_graph(source["board"])

    report["checks"]["source_colour_counts_match"] = (
        dict(sorted(Counter(
            cell for row in source["board"] for cell in row
        ).items()))
        == dict(sorted(source.get("counts", {}).items()))
    )

    path = Path("data/region_graph_latest.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2))

    print("SLIME AI — REGION ADJACENCY GRAPH")
    print("=" * 48)
    print("Grid:", report["grid_size"])
    print("Regions:", report["region_count"])
    print("Shared-border relationships:", len(report["adjacency_edges"]))
    print("Shared border cell-pairs:", report["total_shared_border_edges"])

    print("\nLARGEST REGIONS AND NEIGHBOURS")
    for region in report["regions"][:12]:
        print(
            f"{region['id']} {region['colour']:8} "
            f"size={region['size']:4} "
            f"perimeter={region['perimeter']:4} "
            f"neighbours={region['neighbor_count']:2}"
        )
        for neighbor, edges in sorted(region["neighbors"].items()):
            print(f"    {neighbor}: {edges} shared border cells")

    print("\nCHECKS")
    for name, passed in report["checks"].items():
        print(f"[{'PASS' if passed else 'FAIL'}] {name}")

    print("Gameplay verified:", report["gameplay_verified"])
    print("Game taps enabled:", report["game_taps_enabled"])
    print("Report: data/region_graph_latest.json")

    if not all(report["checks"].values()):
        raise SystemExit("Region graph audit failed.")


if __name__ == "__main__":
    audit_file()
