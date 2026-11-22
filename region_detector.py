import json
from collections import deque, Counter

with open("data/vision_level39.json") as f:
    board = json.load(f)["board"]

H = len(board)
W = len(board[0])
visited = set()

print("CONNECTED COLOUR REGIONS")
print("=" * 55)

regions = []

for y in range(H):
    for x in range(W):
        colour = board[y][x]

        if colour == "cyan" or (y, x) in visited:
            continue

        queue = deque([(y, x)])
        visited.add((y, x))
        cells = []

        while queue:
            cy, cx = queue.popleft()
            cells.append((cy, cx))

            for dy, dx in ((0,1), (0,-1),(1,0),(-1,0)):
                ny, nx = cy + dy, cx + dx

                if not (0 <= ny < H and 0 <= nx < W):
                    continue

                if (ny, nx) in visited:
                    continue

                if board[ny][nx] == colour:
                    visited.add((ny, nx))
                    queue.append((ny, nx))

        ys = [p[0] for p in cells]
        xs = [p[1] for p in cells]

        regions.append({
            "colour": colour,
            "size": len(cells),
            "top": min(ys),
            "bottom": max(ys),
            "left": min(xs),
            "right": max(xs)
        })

for i, r in enumerate(regions, 1):
    print(
        f"{i:02d}. {r['colour']:8} "
        f"size={r['size']:3} "
        f"rows={r['top']}-{r['bottom']} "
        f"cols={r['left']}-{r['right']}"
    )

print("\nTOTAL REGIONS:", len(regions))
print("NON-CYAN CELLS:", sum(r["size"] for r in regions))
