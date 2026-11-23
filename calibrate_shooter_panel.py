#!/usr/bin/env python3
"""Create a coordinate-grid preview for manual shooter-panel calibration.

This utility does not guess or save crop bounds. It creates a labelled preview
so a person can identify the actual panel rectangle in source-image pixels.
"""
import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def create_preview(source, output, step=100, max_width=1400):
    if type(step) is not int or step < 10:
        raise ValueError("Grid step must be an integer of at least 10 pixels")
    if type(max_width) is not int or max_width < 200:
        raise ValueError("Preview width must be an integer of at least 200 pixels")

    source = Path(source)
    output = Path(output)
    if not source.is_file():
        raise FileNotFoundError(source)

    with Image.open(source) as opened:
        image = opened.convert("RGB")
    width, height = image.size
    scale = min(1.0, max_width / width)
    preview_size = (max(1, round(width * scale)),
                    max(1, round(height * scale)))
    preview = image.resize(preview_size, Image.Resampling.LANCZOS)
    draw = ImageDraw.Draw(preview, "RGBA")
    font = ImageFont.load_default()
    pw, ph = preview_size

    for x in range(0, width + 1, step):
        px = min(pw - 1, round(x * scale))
        draw.line((px, 0, px, ph), fill=(255, 255, 255, 110), width=1)
        if x < width:
            draw.rectangle((px + 2, 2, px + 42, 15),
                           fill=(0, 0, 0, 180))
            draw.text((px + 4, 3), str(x), fill=(255, 255, 0, 255),
                      font=font)

    for y in range(0, height + 1, step):
        py = min(ph - 1, round(y * scale))
        draw.line((0, py, pw, py), fill=(255, 255, 255, 110), width=1)
        if y < height:
            draw.rectangle((2, py + 2, 42, py + 15),
                           fill=(0, 0, 0, 180))
            draw.text((4, py + 3), str(y), fill=(0, 255, 255, 255),
                      font=font)

    output.parent.mkdir(parents=True, exist_ok=True)
    preview.save(output)
    return {
        "source_size": [width, height],
        "preview_size": list(preview_size),
        "scale": scale,
        "grid_step_source_pixels": step,
        "output": str(output),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Make a labelled coordinate grid for shooter-panel crop calibration"
    )
    parser.add_argument("screenshot", help="Full, unmodified game screenshot")
    parser.add_argument("--output", default="screenshots/shooter_calibration_grid.png")
    parser.add_argument("--step", type=int, default=100,
                        help="Grid spacing in original screenshot pixels")
    parser.add_argument("--max-width", type=int, default=1400,
                        help="Maximum preview width; coordinates remain source pixels")
    args = parser.parse_args()

    result = create_preview(args.screenshot, args.output, args.step,
                            args.max_width)
    print("SLIME AI — SHOOTER PANEL CALIBRATION PREVIEW")
    print("=" * 48)
    print("Source dimensions:", result["source_size"])
    print("Preview dimensions:", result["preview_size"])
    print("Preview scale:", round(result["scale"], 4))
    print("Grid spacing (source pixels):", result["grid_step_source_pixels"])
    print("Saved:", result["output"])
    print("Read LEFT, TOP, RIGHT, BOTTOM from the source-pixel grid.")
    print("This preview does not infer or approve crop bounds.")


if __name__ == "__main__":
    main()
