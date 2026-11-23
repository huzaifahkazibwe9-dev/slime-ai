from PIL import Image, ImageOps
from pathlib import Path
import numpy as np
import subprocess
import colorsys
import re
import json
import argparse
import hashlib

IMAGE = Path("screenshots/shooter_panel.jpg")
OUTPUT = Path("data/shooter_detection.json")

REF_W, REF_H = 1536, 999

SHOOTERS = [
    {"id": "top_1", "box": (235,150,435,285), "sample": (330,275)},
    {"id": "top_2", "box": (530,150,730,285), "sample": (625,275)},
    {"id": "top_3", "box": (835,150,1035,285), "sample": (930,275)},
    {"id": "top_4", "box": (1135,150,1335,285), "sample": (1230,275)},
]

def validate_panel_image_size(width, height, tolerance=0.02):
    if type(width) is not int or type(height) is not int or width < 1 or height < 1:
        raise ValueError("Shooter panel image dimensions must be positive integers")
    expected_ratio = REF_W / REF_H
    actual_ratio = width / height
    if abs(actual_ratio - expected_ratio) / expected_ratio > tolerance:
        raise ValueError(
            "Shooter panel aspect ratio does not match the calibrated panel crop"
        )
    return True


def scale_point(p, sx, sy):
    return round(p[0]*sx), round(p[1]*sy)

def scale_box(b, sx, sy):
    return tuple(round(v*(sx if i%2==0 else sy))
                 for i,v in enumerate(b))

def identify_color(rgb):
    r,g,b = [v/255 for v in rgb]
    h,s,v = colorsys.rgb_to_hsv(r,g,b)
    hue = h*360

    if v < 0.18:
        name = "black"
    elif s < 0.16 and v > 0.88:
        name = "white"
    elif s < 0.18:
        name = "gray"
    elif hue < 15 or hue >= 345:
        name = "red"
    elif hue < 40 and v < 0.82:
        name = "brown"
    elif hue < 40:
        name = "orange"
    elif hue < 65:
        name = "yellow"
    elif hue < 165:
        name = "green"
    elif hue < 200:
        name = "cyan"
    elif hue < 255:
        name = "blue"
    elif hue < 290:
        name = "purple"
    elif hue < 345:
        name = "magenta"
    else:
        name = "unknown"

    return {
        "name": name,
        "rgb": list(rgb),
        "hex": "#{:02X}{:02X}{:02X}".format(*rgb),
        "hsv": [
            round(hue,1),
            round(s*100,1),
            round(v*100,1)
        ],
        "hue_group": round(hue/15)*15 if s >= 0.16 else None
    }

def read_ammunition(image, box, temp):
    crop = image.crop(box).convert("L")
    crop = ImageOps.autocontrast(crop)
    crop = crop.resize((600,405))
    crop.save(temp)

    try:
        result = subprocess.run(
            [
                "tesseract", str(temp), "stdout",
                "--psm", "6",
                "-c", "tessedit_char_whitelist=0123456789"
            ],
            capture_output=True,
            text=True,
            timeout=15
        )
    except (OSError, subprocess.SubprocessError):
        return None

    if result.returncode != 0 or not isinstance(result.stdout, str):
        return None

    digits = re.findall(r"\d+", result.stdout)
    return int(digits[0]) if len(digits) == 1 else None

def verify_panel_crop(source_path, panel_path, bounds, mean_tolerance=14, percentile_tolerance=48):
    """Verify a panel image against a region of the full source screenshot.

    Resizing and JPEG recompression are expected in the panel-crop workflow.
    The crop's aspect ratio must remain calibrated, and pixel differences are
    bounded using robust mean and 99th-percentile thresholds.
    """
    if (not isinstance(bounds, (list, tuple)) or len(bounds) != 4
            or any(type(v) is not int for v in bounds)):
        raise ValueError("Panel bounds must be four integer coordinates")
    left, top, right, bottom = bounds
    with Image.open(source_path) as source, Image.open(panel_path) as panel:
        source = source.convert("RGB")
        panel = panel.convert("RGB")
        if not (0 <= left < right <= source.width
                and 0 <= top < bottom <= source.height):
            raise ValueError("Panel bounds are outside the source screenshot")
        crop = source.crop((left, top, right, bottom))
        expected_ratio = crop.width / crop.height
        actual_ratio = panel.width / panel.height
        if abs(expected_ratio - actual_ratio) / expected_ratio > 0.02:
            raise ValueError("Panel crop aspect ratio does not match source region")
        if crop.size != panel.size:
            crop = crop.resize(panel.size, Image.Resampling.LANCZOS)
        delta = np.abs(
            np.asarray(crop, dtype=np.int16)
            - np.asarray(panel, dtype=np.int16)
        )
        if delta.size:
            mean_difference = float(delta.mean())
            percentile_difference = float(np.percentile(delta, 99))
            if (mean_difference > mean_tolerance
                    or percentile_difference > percentile_tolerance):
                raise ValueError(
                    "Panel image does not match the supplied screenshot region "
                    f"(mean={mean_difference:.2f}, p99={percentile_difference:.2f})"
                )
    return hashlib.sha256(Path(source_path).read_bytes()).hexdigest()

def extract_panel_crop(source_path, bounds, output_path=IMAGE):
    """Create the calibrated shooter panel image from a full screenshot."""
    if (not isinstance(bounds, (list, tuple)) or len(bounds) != 4
            or any(type(v) is not int for v in bounds)):
        raise ValueError("Panel bounds must be four integer coordinates")
    left, top, right, bottom = bounds
    with Image.open(source_path) as source:
        source = source.convert("RGB")
        if not (0 <= left < right <= source.width
                and 0 <= top < bottom <= source.height):
            raise ValueError("Panel bounds are outside the source screenshot")
        crop = source.crop((left, top, right, bottom))
        expected_ratio = REF_W / REF_H
        actual_ratio = crop.width / crop.height
        if abs(actual_ratio - expected_ratio) / expected_ratio > 0.02:
            raise ValueError("Selected source region does not match shooter panel aspect ratio")
        crop = crop.resize((REF_W, REF_H), Image.Resampling.LANCZOS)
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        crop.save(output_path, quality=95)
    return output_path

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-screenshot")
    parser.add_argument("--panel-bounds", nargs=4, type=int)
    parser.add_argument("--capture-session-id")
    parser.add_argument("--captured-at")
    parser.add_argument("--extract-panel", action="store_true")
    args = parser.parse_args()

    if bool(args.source_screenshot) != bool(args.panel_bounds):
        raise ValueError("--source-screenshot and --panel-bounds must be supplied together")
    if args.extract_panel and not args.source_screenshot:
        raise ValueError("--extract-panel requires --source-screenshot and --panel-bounds")
    if args.extract_panel:
        extract_panel_crop(args.source_screenshot, args.panel_bounds, IMAGE)

    if not IMAGE.exists():
        raise FileNotFoundError(IMAGE)

    image = Image.open(IMAGE).convert("RGB")
    validate_panel_image_size(image.width, image.height)
    sx = image.width/REF_W
    sy = image.height/REF_H

    detected = []
    temp = Path("screenshots/ocr_temp.png")

    for shooter in SHOOTERS:
        x,y = scale_point(shooter["sample"],sx,sy)
        box = scale_box(shooter["box"], sx, sy)

        if not (4 <= x < image.width - 4 and 4 <= y < image.height - 4):
            raise ValueError(f"Shooter sample for {shooter['id']} is outside the panel")
        if not (
            0 <= box[0] < box[2] <= image.width
            and 0 <= box[1] < box[3] <= image.height
        ):
            raise ValueError(f"Ammo OCR box for {shooter['id']} is outside the panel")

        patch = image.crop((x-4,y-4,x+5,y+5))
        pixels = np.asarray(patch,dtype=np.uint8)
        rgb = tuple(
            int(round(v))
            for v in np.median(pixels,axis=(0,1))
        )

        color = identify_color(rgb)
        ammo = read_ammunition(
            image,
            scale_box(shooter["box"],sx,sy),
            temp
        )

        center = (
            round((box[0] + box[2]) / 2),
            round((box[1] + box[3]) / 2)
        )

        detected.append({
            "id": shooter["id"],
            "color": color,
            "ammo": ammo,
            "screen_center": list(center),
            "screen_box": list(box),
            "screen_sample": [x, y],
            "status": "visible",
            "verified": False
        })

    # User-confirmed bonded shooter relationships
    bonded_groups = [
        ["top_1", "top_2"],
        ["top_3", "top_4"]
    ]

    for shooter in detected:
        shooter["bonded_ids"] = []

    for group in bonded_groups:
        for shooter_id in group:
            shooter = next(
                s for s in detected
                if s["id"] == shooter_id
            )
            shooter["bonded_ids"] = [
                member for member in group
                if member != shooter_id
            ]

    temp.unlink(missing_ok=True)

    provenance = {
        "verified": False,
        "source_sha256": None,
        "capture_session_id": None,
        "captured_at": None,
    }
    if args.source_screenshot:
        from capture_provenance import (
            parse_aware_capture_timestamp,
            validate_capture_session_id,
        )
        source_hash = verify_panel_crop(
            args.source_screenshot, IMAGE, args.panel_bounds
        )
        session_id = validate_capture_session_id(args.capture_session_id)
        captured_at = parse_aware_capture_timestamp(args.captured_at)
        provenance = {
            "verified": bool(session_id and captured_at),
            "source_sha256": source_hash,
            "capture_session_id": session_id,
            "captured_at": captured_at,
        }

    result = {
        "capture_provenance": provenance,
        "image_dimensions": list(image.size),
        "visible_shooters": detected,
        "bonded_groups": bonded_groups,
        "bonding_source": "user_confirmed",
        "unrevealed_shooters": [
            {
                "id": f"question_{i}",
                "color": None,
                "ammo": None,
                "status": "unrevealed"
            }
            for i in range(1,5)
        ],
        "lower_shooters": {
            "status": "partially_occluded",
            "color": None,
            "ammo": None
        }
    }

    OUTPUT.parent.mkdir(exist_ok=True)
    OUTPUT.write_text(json.dumps(result,indent=2))

    print("\nSLIME AI — DYNAMIC COLOUR DETECTOR")
    print("="*40)

    for s in detected:
        print(
            s["id"],
            "|",s["color"]["name"],
            "|",s["color"]["hex"],
            "| ammo:",s["ammo"]
        )

    print("\nSaved:",OUTPUT)

if __name__ == "__main__":
    main()
