import json
from strict_json import strict_json_loads
import colorsys
from collections import Counter
from pathlib import Path

VISION_FILE = Path("data/vision_level39.json")
REPORT_FILE = Path("data/vision_validation_report.json")

def classify_rgb(rgb):
    r, g, b = [v / 255 for v in rgb]
    hue, saturation, value = colorsys.rgb_to_hsv(r, g, b)
    degrees = hue * 360

    if value < 0.22:
        return "dark"
    if saturation < 0.18:
        return "white" if value > 0.72 else "gray"
    if degrees < 12 or degrees >= 345:
        return "red"
    elif degrees < 38:
        return "orange"
    elif degrees < 68:
        return "yellow"
    elif degrees < 165:
        return "green"
    elif degrees < 205:
        return "cyan"
    elif degrees < 260:
        return "blue"
    elif degrees < 300:
        return "purple"
    return "pink"

def audit_data(data):
    errors = []
    warnings = []

    board = data.get("board")
    rgb_grid = data.get("raw_rgb")
    grid_size = data.get("grid_size")

    if (not isinstance(grid_size, list) or len(grid_size) != 2
            or any(type(value) is not int or value < 1
                   for value in grid_size)):
        return {"passed": False, "errors": ["Invalid grid_size"]}

    width, height = grid_size
    if not isinstance(board, list) or len(board) != height:
        errors.append("Board height mismatch")
    if not isinstance(rgb_grid, list) or len(rgb_grid) != height:
        errors.append("RGB grid height mismatch")

    if errors:
        return {"passed": False, "errors": errors}

    counts = Counter()
    mismatches = []
    samples_checked = 0

    for y in range(height):
        if not isinstance(board[y], list) or len(board[y]) != width:
            errors.append(f"Board row {y} has incorrect width")
            continue
        if not isinstance(rgb_grid[y], list) or len(rgb_grid[y]) != width:
            errors.append(f"RGB row {y} has incorrect width")
            continue

        for x in range(width):
            label = board[y][x]
            rgb = rgb_grid[y][x]

            if not isinstance(label, str) or not label:
                errors.append(f"Invalid label at ({x},{y})")
                continue

            if (not isinstance(rgb, list) or len(rgb) != 3
                    or any(type(v) is not int or v < 0 or v > 255
                           for v in rgb)):
                errors.append(f"Invalid RGB sample at ({x},{y})")
                continue

            samples_checked += 1
            counts[label] += 1
            calculated = classify_rgb(rgb)

            if calculated != label:
                mismatches.append({
                    "row": y,
                    "column": x,
                    "saved_label": label,
                    "calculated_label": calculated,
                    "rgb": rgb
                })

    saved_counts = data.get("counts", {})
    counts_match = (
        isinstance(saved_counts, dict) and dict(counts) == saved_counts
    )

    if not counts_match:
        errors.append("Saved colour counts do not match board labels")

    expected_cells = width * height
    if samples_checked != expected_cells:
        errors.append(
            f"Expected {expected_cells} valid samples; found {samples_checked}"
        )

    if mismatches:
        warnings.append(
            f"{len(mismatches)} saved labels differ from recalculated labels"
        )

    occupancy = data.get("occupancy", {})
    occupancy_confirmed = (
        isinstance(occupancy, dict)
        and occupancy.get("initial_occupancy_user_confirmed") is True
    )

    return {
        "passed": not errors and not mismatches,
        "grid_size": [width, height],
        "expected_cells": expected_cells,
        "valid_rgb_samples": samples_checked,
        "saved_counts_match": counts_match,
        "recalculated_counts": dict(counts),
        "classification_mismatch_count": len(mismatches),
        "classification_mismatch_examples": mismatches[:20],
        "initial_occupancy_user_confirmed": occupancy_confirmed,
        "vision_classification_verified": False,
        "gameplay_colour_mapping_verified": False,
        "gameplay_taps_enabled": False,
        "errors": errors,
        "warnings": warnings,
        "interpretation": (
            "This audit checks data integrity and consistency with the "
            "existing colour-classification algorithm. It does not prove "
            "that the algorithm correctly identifies real game colours."
        )
    }

def main():
    if not VISION_FILE.exists():
        raise FileNotFoundError(VISION_FILE)

    data = strict_json_loads(VISION_FILE.read_text())
    report = audit_data(data)
    REPORT_FILE.write_text(json.dumps(report, indent=2))

    print("SLIME AI — INDEPENDENT VISION DATA AUDIT")
    print("=" * 48)
    print("Grid:", report.get("grid_size"))
    print("Expected cells:", report.get("expected_cells"))
    print("Valid RGB samples:", report.get("valid_rgb_samples"))
    print("Saved counts match:", report.get("saved_counts_match"))
    print("Classification mismatches:",
          report.get("classification_mismatch_count"))
    print("Occupancy user-confirmed:",
          report.get("initial_occupancy_user_confirmed"))
    print("Vision classification verified: False")
    print("Gameplay mappings verified: False")
    print("Gameplay taps enabled: False")

    for error in report.get("errors", []):
        print("[ERROR]", error)
    for warning in report.get("warnings", []):
        print("[WARNING]", warning)

    print("\nRESULT:", "PASS" if report["passed"] else "FAIL")
    print("Report:", REPORT_FILE)

if __name__ == "__main__":
    main()
