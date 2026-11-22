import json
from PIL import Image, ImageDraw

with open("data/vision_level39.json") as f:
    data = json.load(f)

board = data["board"]

COLOURS = {
    "cyan": (100, 195, 230),
    "white": (255, 255, 255),
    "red": (230, 65, 65),
    "blue": (40, 120, 240),
    "green": (120, 220, 70),
    "yellow": (255, 210, 60),
    "orange": (200, 120, 60),
    "pink": (255, 150, 230),
    "purple": (210, 50, 230),
    "gray": (130, 130, 140),
}

CELL = 24
H = len(board)
W = len(board[0])

img = Image.new("RGB", (W * CELL, H * CELL), "black")
draw = ImageDraw.Draw(img)

for y, row in enumerate(board):
    for x, colour in enumerate(row):
        x1, y1 = x * CELL, y * CELL
        x2, y2 = x1 + CELL, y1 + CELL

        draw.rectangle(
            (x1, y1, x2, y2),
            fill=COLOURS.get(colour, (0, 0, 0)),
            outline=(40, 40, 40)
        )

img.save("screenshots/board_map.png")

print("Saved: screenshots/board_map.png")
print("Dimensions:", img.size)
