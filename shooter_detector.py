from PIL import Image, ImageOps
from pathlib import Path
import numpy as np
import subprocess
import colorsys
import re
import json
import argparse
import hashlib
import time
import math

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
    if (type(tolerance) not in (int, float) or not math.isfinite(tolerance)
            or not 0 < tolerance <= 1):
        raise ValueError("Aspect-ratio tolerance must be finite and in (0, 1]")
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

def assess_color_sample(image, x, y, patch_radius=4, context_radius=8,
                        minimum_contrast=24.0, maximum_mad=32.0):
    """Measure whether a fixed sample is distinct from its local context.

    This is a quality flag, not a shooter identity or colour verification.
    """
    if any(type(v) is not int for v in (x, y, patch_radius, context_radius)):
        raise ValueError("Sample coordinates and radii must be integers")
    if patch_radius < 1 or context_radius <= patch_radius:
        raise ValueError("Sample radii are invalid")
    if (type(minimum_contrast) not in (int, float)
            or not math.isfinite(minimum_contrast)
            or not 0 <= minimum_contrast <= 441.673):
        raise ValueError("Minimum contrast must be finite and within RGB distance bounds")
    if (type(maximum_mad) not in (int, float)
            or not math.isfinite(maximum_mad)
            or not 0 <= maximum_mad <= 255):
        raise ValueError("Maximum MAD must be finite and within channel bounds")
    if not (context_radius <= x < image.width - context_radius
            and context_radius <= y < image.height - context_radius):
        raise ValueError("Sample context is outside the panel image")

    pixels = np.asarray(
        image.crop((x-patch_radius, y-patch_radius,
                    x+patch_radius+1, y+patch_radius+1)),
        dtype=np.float32,
    )
    context = np.asarray(
        image.crop((x-context_radius, y-context_radius,
                    x+context_radius+1, y+context_radius+1)),
        dtype=np.float32,
    )
    mask = np.ones(context.shape[:2], dtype=bool)
    start = context_radius - patch_radius
    stop = context_radius + patch_radius + 1
    mask[start:stop, start:stop] = False
    centre_rgb = np.median(pixels, axis=(0, 1))
    context_rgb = np.median(context[mask], axis=0)
    mad = float(np.median(np.abs(pixels - centre_rgb)))
    contrast = float(np.linalg.norm(centre_rgb - context_rgb))
    distinct = contrast >= minimum_contrast and mad <= maximum_mad
    return {
        "status": "DISTINCT_SAMPLE" if distinct else "LOW_CONFIDENCE_SAMPLE",
        "local_contrast": round(contrast, 2),
        "median_absolute_deviation": round(mad, 2),
        "method": "centre_patch_vs_local_context",
        "thresholds": {
            "minimum_contrast": minimum_contrast,
            "maximum_median_absolute_deviation": maximum_mad,
        },
    }


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
    for name, value in (
        ("mean_tolerance", mean_tolerance),
        ("percentile_tolerance", percentile_tolerance),
    ):
        if (type(value) not in (int, float)
                or not math.isfinite(value)
                or not 0 <= value <= 255):
            raise ValueError(
                f"{name} must be finite and within per-channel difference bounds [0, 255]"
            )
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

def load_user_confirmed_bonded_groups(path, shooter_ids):
    """Load bonds only from an explicit, user-confirmed local config."""
    path = Path(path)
    if not path.is_file():
        return [], "not_configured"

    data = json.loads(path.read_text())
    if not isinstance(data, dict):
        raise ValueError("Bonded-group config must be a JSON object")
    if data.get("verified_by_user") is not True:
        return [], "not_user_confirmed"

    groups = data.get("bonded_groups")
    if not isinstance(groups, list):
        raise ValueError("bonded_groups must be a list")
    known_ids = set(shooter_ids)
    grouped_ids = set()
    for index, group in enumerate(groups):
        if not isinstance(group, list):
            raise ValueError(f"Bonded group {index} must be a list")
        if len(group) < 2 or len(group) > 3:
            raise ValueError(f"Bonded group {index} must contain 2 or 3 shooters")
        if any(not isinstance(member, str) or not member for member in group):
            raise ValueError(f"Bonded group {index} contains an invalid shooter ID")
        if len(group) != len(set(group)):
            raise ValueError(f"Bonded group {index} contains duplicate shooter IDs")
        unknown = set(group) - known_ids
        if unknown:
            raise ValueError(
                f"Bonded group {index} references unknown shooters: "
                + ", ".join(sorted(unknown))
            )
        overlap = grouped_ids.intersection(group)
        if overlap:
            raise ValueError(
                "A shooter cannot belong to multiple bonded groups: "
                + ", ".join(sorted(overlap))
            )
        grouped_ids.update(group)
    return groups, "user_confirmed"


def build_panel_slot_inventory(image_width, image_height):
    """Describe every slot in the calibrated multi-row shooter panel.

    Only the first row is currently readable by the legacy colour/ammo
    detector. Later rows remain explicitly unrevealed or occluded; they are
    never promoted to selectable shooters until a dedicated detector verifies
    their contents.
    """
    if (type(image_width) is not int or type(image_height) is not int
            or image_width < 1 or image_height < 1):
        raise ValueError("Panel dimensions must be positive integers")

    sx = image_width / REF_W
    sy = image_height / REF_H
    x_centres = [item["sample"][0] for item in SHOOTERS]
    row_specs = [
        ("visible", 275, "readable"),
        ("question", 575, "unrevealed"),
        ("lower", 875, "partially_occluded"),
    ]
    slots = []
    for row_index, (prefix, y, status) in enumerate(row_specs, start=1):
        for column_index, x in enumerate(x_centres, start=1):
            if row_index == 1:
                slot_id = SHOOTERS[column_index - 1]["id"]
            else:
                slot_id = f"{prefix}_{column_index}"
            slots.append({
                "id": slot_id,
                "row": row_index,
                "column": column_index,
                "center": list(scale_point((x, y), sx, sy)),
                "status": status,
                "selectable_candidate": False,
            })
    return slots


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
    slot_observations = []
    temp = Path("screenshots/ocr_temp.png")
    detection_started = time.perf_counter()
    ocr_seconds = 0.0
    ocr_calls = 0

    # Observe every row, but keep lower-row records non-selectable until verified.
    row_specs = [
        ("visible", 0, "readable_candidate"),
        ("question", 300, "unrevealed_candidate"),
        ("lower", 600, "partially_occluded_candidate"),
    ]
    for row_index, (prefix, y_offset, row_status) in enumerate(row_specs, start=1):
        for shooter in SHOOTERS:
            column = int(shooter["id"].split("_")[-1])
            shooter_id = shooter["id"] if row_index == 1 else f"{prefix}_{column}"
            sample_ref = (shooter["sample"][0], shooter["sample"][1] + y_offset)
            box_ref = (shooter["box"][0], shooter["box"][1] + y_offset,
                       shooter["box"][2], shooter["box"][3] + y_offset)
            x, y = scale_point(sample_ref, sx, sy)
            box = scale_box(box_ref, sx, sy)
            if not (4 <= x < image.width - 4 and 4 <= y < image.height - 4):
                raise ValueError(f"Panel sample for {shooter_id} is outside the panel")
            if not (0 <= box[0] < box[2] <= image.width
                    and 0 <= box[1] < box[3] <= image.height):
                raise ValueError(f"Panel OCR box for {shooter_id} is outside the panel")
            pixels = np.asarray(image.crop((x-4, y-4, x+5, y+5)), dtype=np.uint8)
            rgb = tuple(int(round(v)) for v in np.median(pixels, axis=(0, 1)))
            color = identify_color(rgb)
            sample_quality = assess_color_sample(image, x, y)
            # Lower rows are observed for colour/layout, but are not yet
            # readable/selectable. Avoid launching OCR for unverified slots.
            ammo = None
            if row_index == 1:
                ocr_started = time.perf_counter()
                ammo = read_ammunition(image, box, temp)
                ocr_seconds += time.perf_counter() - ocr_started
                ocr_calls += 1
            center = (round((box[0] + box[2]) / 2),
                      round((box[1] + box[3]) / 2))
            slot_observations.append({
                "id": shooter_id, "row": row_index, "column": column,
                "color_observation": color, "sample_quality": sample_quality,
                "ammunition_observation": ammo,
                "screen_center": list(center), "screen_box": list(box),
                "screen_sample": [x, y], "status": row_status,
                "verified": False, "selectable_candidate": False,
            })
            if row_index == 1:
                detected.append({
                    "id": shooter_id, "color": color,
                    "sample_quality": sample_quality, "ammo": ammo,
                    "screen_center": list(center), "screen_box": list(box),
                    "screen_sample": [x, y], "status": "visible", "verified": False
                })

    # Bond relationships are never inferred from fixed screen positions.
    # They are loaded only from a separate, explicit user-confirmed file.
    bonded_groups, bonding_source = load_user_confirmed_bonded_groups(
        "data/bonded_groups_confirmed.json",
        [shooter["id"] for shooter in detected],
    )

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

    panel_slots = build_panel_slot_inventory(image.width, image.height)
    detection_seconds = time.perf_counter() - detection_started

    result = {
        "performance": {
            "shooter_detection_seconds": round(detection_seconds, 6),
            "ammunition_ocr_seconds": round(ocr_seconds, 6),
            "ammunition_ocr_calls": ocr_calls,
            "panel_slots_observed": len(slot_observations),
            "timing_clock": "perf_counter",
            "note": "Local processing measurements; not a device-wide gameplay latency benchmark.",
        },
        "capture_provenance": provenance,
        "panel_layout": {"rows": 3, "columns": 4, "slot_count": 12},
        "panel_slots": panel_slots,
        "panel_slot_observations": slot_observations,
        "bond_relationships": {
            "status": "requires_user_confirmation",
            "verified_groups": bonded_groups,
            "automatically_inferred": False,
        },
        "image_dimensions": list(image.size),
        "visible_shooters": detected,
        "bonded_groups": bonded_groups,
        "bonding_source": bonding_source,
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
