#!/usr/bin/env python3
"""Independent validation of calibrated shooter-to-board geometry."""

import json
from pathlib import Path

from conveyor_geometry import calculate_firing_geometry, load_verified_calibration

ROOT = Path(__file__).resolve().parent
CALIBRATION = ROOT / "data" / "conveyor_calibration.json"
OUTPUT = ROOT / "data" / "geometry_validation_latest.json"

EXPECTED = {
    "bottom_1": {"lane": 10, "direction": "up", "first": [10, 34]},
    "bottom_2": {"lane": 17, "direction": "up", "first": [17, 34]},
    "right_1": {"lane": 12, "direction": "left", "first": [34, 12]},
    "right_2": {"lane": 19, "direction": "left", "first": [34, 19]},
    "top_1": {"lane": 27, "direction": "down", "first": [27, 0]},
    "top_2": {"lane": 33, "direction": "down", "first": [33, 0]},
    "left_1": {"lane": 2, "direction": "right", "first": [0, 2]},
    "left_2": {"lane": 9, "direction": "right", "first": [0, 9]},
}


def validate_calibration(data):
    if data.get("verified_by_user") is not True:
        raise ValueError("Calibration is not user-confirmed.")

    width, height = data["image_size"]
    cols, rows = data["board_grid"]

    if width <= 0 or height <= 0 or cols <= 0 or rows <= 0:
        raise ValueError("Invalid image or board dimensions.")

    shooters = data["shooters"]
    ids = [item["id"] for item in shooters]

    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate shooter IDs detected.")

    if set(ids) != set(EXPECTED):
        raise ValueError("Shooter IDs do not match expected calibration.")

    results = []

    for item in shooters:
        shooter_id = item["id"]
        segment = item["segment"]
        x, y = item["center"]

        if not (0 <= x < width and 0 <= y < height):
            raise ValueError(f"{shooter_id}: centre outside screenshot.")

        result = calculate_firing_geometry(
            screen_center=(x, y),
            segment=segment,
            image_size=(width, height),
            position_verified=True,
        )

        direction = result["direction"]

        if direction != data["directions"].get(segment):
            raise ValueError(f"{shooter_id}: direction mapping mismatch.")

        if direction not in ("up", "down", "left", "right"):
            raise ValueError(f"{shooter_id}: invalid direction.")

        first_x, first_y = result["first_board_cell"]

        if not (0 <= first_x < cols and 0 <= first_y < rows):
            raise ValueError(f"{shooter_id}: first cell outside board.")

        expected = EXPECTED[shooter_id]
        lane = (
            result["origin"][0]
            if segment in ("bottom", "top")
            else result["origin"][1]
        )

        if lane != expected["lane"]:
            raise ValueError(f"{shooter_id}: unexpected calculated lane.")

        if list(result["first_board_cell"]) != expected["first"]:
            raise ValueError(f"{shooter_id}: unexpected first board cell.")

        results.append({
            "id": shooter_id,
            "segment": segment,
            "screen_center": [x, y],
            "direction": direction,
            "calculated_lane": lane,
            "first_board_cell": list(result["first_board_cell"]),
            "screen_position_verified": True,
            "direction_mapping_consistent": True,
            "actual_firing_verified": False,
            "gameplay_access_enabled": False,
        })

    return {
        "image_size": [width, height],
        "board_grid": [cols, rows],
        "shooters_checked": len(results),
        "all_coordinate_checks_passed": True,
        "actual_firing_verified": False,
        "gameplay_access_enabled": False,
        "results": results,
    }


def run_tests(report):
    tests = []

    def check(name, condition):
        tests.append((name, bool(condition)))

    check(
        "All eight calibrated shooters checked",
        report["shooters_checked"] == 8,
    )
    check(
        "All calculated entry lanes match expected values",
        all(
            item["calculated_lane"] == EXPECTED[item["id"]]["lane"]
            for item in report["results"]
        ),
    )
    check(
        "All first board cells are within the board",
        all(
            0 <= item["first_board_cell"][0] < 35
            and 0 <= item["first_board_cell"][1] < 35
            for item in report["results"]
        ),
    )
    check(
        "Actual firing remains explicitly unverified",
        report["actual_firing_verified"] is False
        and all(
            item["actual_firing_verified"] is False
            for item in report["results"]
        ),
    )
    check(
        "Gameplay access remains disabled",
        report["gameplay_access_enabled"] is False
        and all(
            item["gameplay_access_enabled"] is False
            for item in report["results"]
        ),
    )

    print("GEOMETRY VALIDATION TESTS")
    print("=" * 48)

    passed = 0

    for name, success in tests:
        print(f"[{'PASS' if success else 'FAIL'}] {name}")
        passed += int(success)

    print(f"\nTests passed: {passed}/{len(tests)}")

    if passed != len(tests):
        raise RuntimeError("Geometry validation failed.")


def main():
    data = load_verified_calibration(CALIBRATION)
    report = validate_calibration(data)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, indent=2))

    run_tests(report)

    print("\nCALIBRATED SHOOTER LANES")
    print("=" * 48)

    for item in report["results"]:
        print(
            f"{item['id']:10} "
            f"direction={item['direction']:5} "
            f"lane={item['calculated_lane']:2} "
            f"first_cell={item['first_board_cell']}"
        )

    print("\nReport:", OUTPUT)
    print("Actual firing verified: NO")
    print("Gameplay access enabled: NO")


if __name__ == "__main__":
    main()
