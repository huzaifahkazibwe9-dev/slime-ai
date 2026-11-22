from PIL import Image, ImageOps
from pathlib import Path
import numpy as np
import subprocess
import colorsys
import re
import json

IMAGE = Path("screenshots/shooter_panel.jpg")
OUTPUT = Path("data/shooter_detection.json")

REF_W, REF_H = 1536, 999

SHOOTERS = [
    {"id": "top_1", "box": (235,150,435,285), "sample": (330,275)},
    {"id": "top_2", "box": (530,150,730,285), "sample": (625,275)},
    {"id": "top_3", "box": (835,150,1035,285), "sample": (930,275)},
    {"id": "top_4", "box": (1135,150,1335,285), "sample": (1230,275)},
]

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

    digits = re.findall(r"\d+", result.stdout)
    return int(digits[0]) if len(digits)==1 else None

def main():
    if not IMAGE.exists():
        raise FileNotFoundError(IMAGE)

    image = Image.open(IMAGE).convert("RGB")
    sx = image.width/REF_W
    sy = image.height/REF_H

    detected = []
    temp = Path("screenshots/ocr_temp.png")

    for shooter in SHOOTERS:
        x,y = scale_point(shooter["sample"],sx,sy)

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

        box = scale_box(shooter["box"], sx, sy)

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

    result = {
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
