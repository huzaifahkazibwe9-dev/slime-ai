from PIL import Image, ImageDraw

img = Image.open("screenshots/level39.jpg").convert("RGBA")
overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
draw = ImageDraw.Draw(overlay)

left, right = 201, 881
top, bottom = 431, 1113

for i in range(36):
    x = round(left + i * (right-left) / 35)
    y = round(top + i * (bottom-top) / 35)

    draw.line((x, top, x, bottom), fill=(255, 0, 0, 150), width=2)
    draw.line((left, y, right, y), fill=(255, 0, 0, 150), width=2)

result = Image.alpha_composite(img, overlay).convert("RGB")
result.save("screenshots/grid_check.jpg", quality=95)

print("Grid overlay created.")
