#!/usr/bin/env python3
"""Passively compare manually observed firing behaviour with calibrated geometry."""

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CALIBRATION = ROOT / "data" / "conveyor_calibration.json"
OUTPUT = ROOT / "data" / "firing_observations.json"

EXPECTED = {
    "bottom_1": {"lane": 10, "direction": "up"},
    "bottom_2": {"lane": 17, "direction": "up"},
    "right_1": {"lane": 12, "direction": "left"},
    "right_2": {"lane": 19, "direction": "left"},
    "top_1": {"lane": 27, "direction": "down"},
    "top_2": {"lane": 33, "direction": "down"},
    "left_1": {"lane": 2, "direction": "right"},
    "left_2": {"lane": 9, "direction": "right"},
}


def validate_observation(position_id, direction, cell, before, after,
                         directly_observed):
    if position_id not in EXPECTED:
        return False, "Unknown calibration position."

    if directly_observed is not True:
        return False, "Direct observation was not confirmed."

    expected = EXPECTED[position_id]

    if direction not in ("up", "down", "left", "right"):
        return False, "Invalid observed direction."

    if direction != expected["direction"]:
        return False, "Observed direction differs from calibration."

    if not isinstance(cell, (list, tuple)) or len(cell) != 2:
        return False, "First changed cell must be [x, y]."

    x, y = cell
    if not all(isinstance(v, int) and not isinstance(v, bool) for v in cell):
        return False, "Cell coordinates must be integers."

    if not (0 <= x < 35 and 0 <= y < 35):
        return False, "Changed cell is outside the 35x35 board."

    observed_lane = x if position_id.startswith(("top_", "bottom_")) else y
    if observed_lane != expected["lane"]:
        return False, "Changed cell does not lie in the predicted lane."

    if not all(isinstance(v, int) and not isinstance(v, bool)
               for v in (before, after)):
        return False, "Ammo values must be integers."

    if before <= 0 or after < 0 or after >= before:
        return False, "Ammo must decrease between observations."

    return True, "Observation is consistent with calibrated geometry."


def run_tests():
    tests = [
        ("Valid bottom observation",
         validate_observation("bottom_1", "up", [10, 20], 40, 39, True)[0]),
        ("Wrong direction rejected",
         not validate_observation("bottom_1", "down", [10, 20], 40, 39, True)[0]),
        ("Wrong lane rejected",
         not validate_observation("bottom_1", "up", [11, 20], 40, 39, True)[0]),
        ("No ammo decrease rejected",
         not validate_observation("bottom_1", "up", [10, 20], 40, 40, True)[0]),
        ("Unconfirmed observation rejected",
         not validate_observation("bottom_1", "up", [10, 20], 40, 39, False)[0]),
        ("Out-of-board cell rejected",
         not validate_observation("top_1", "down", [27, 35], 40, 39, True)[0]),
    ]

    print("FIRING OBSERVATION TESTS")
    print("=" * 46)
    for name, passed in tests:
        print(f"[{'PASS' if passed else 'FAIL'}] {name}")

    count = sum(passed for _, passed in tests)
    print(f"\nTests passed: {count}/{len(tests)}")
    if count != len(tests):
        raise RuntimeError("Observation tests failed.")


def ask_int(prompt):
    while True:
        try:
            return int(input(prompt).strip())
        except ValueError:
            print("Enter a whole number.")


def main():
    calibration = json.loads(CALIBRATION.read_text())
    if calibration.get("verified_by_user") is not True:
        raise ValueError("User-confirmed calibration is required.")

    run_tests()

    print("\nPASSIVE OBSERVATION")
    print("Use an existing game session if available.")
    print("Do not start a level just to collect this observation.")
    print("No taps or game controls will be issued.\n")

    print("Available calibration positions:")
    for key, value in EXPECTED.items():
        print(f"  {key:10} {value['direction']:5} lane {value['lane']}")

    position_id = input("\nPosition ID: ").strip()
    if position_id not in EXPECTED:
        print("Unknown position. No record saved.")
        return

    print("\nWatch the shooter at this calibrated position.")
    confirmed = input(
        "Did you directly observe this shooter fire from this position? (yes/no): "
    ).strip().lower() == "yes"

    direction = input("Observed firing direction (up/down/left/right): ").strip().lower()
    x = ask_int("X coordinate of first changed board cell (0-34): ")
    y = ask_int("Y coordinate of first changed board cell (0-34): ")
    before = ask_int("Ammo before firing: ")
    after = ask_int("Ammo after firing: ")
    screenshot = input("Screenshot filename (optional): ").strip()

    valid, message = validate_observation(
        position_id, direction, [x, y], before, after, confirmed
    )

    print("\nRESULT:", message)
    if not valid:
        print("No observation saved.")
        return

    data = {"version": 1, "observations": []}
    if OUTPUT.exists():
        data = json.loads(OUTPUT.read_text())

    record = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "position_id": position_id,
        "observed_direction": direction,
        "first_changed_cell": [x, y],
        "ammo_before": before,
        "ammo_after": after,
        "ammo_decrease": before - after,
        "screenshot": screenshot or None,
        "directly_observed": True,
        "observation_status": "consistent_with_calibration",
        "gameplay_access_enabled": False,
    }

    data.setdefault("observations", []).append(record)

    consistent_positions = sorted({
        item["position_id"]
        for item in data["observations"]
        if item.get("observation_status") == "consistent_with_calibration"
    })

    data["positions_observed_consistent"] = consistent_positions
    data["positions_remaining"] = sorted(set(EXPECTED) - set(consistent_positions))
    data["all_eight_positions_observed"] = len(consistent_positions) == 8
    data["actual_firing_fully_verified"] = False
    data["gameplay_access_enabled"] = False

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(data, indent=2))

    print("\nObservation saved:", OUTPUT)
    print("Consistent positions:", len(consistent_positions), "/ 8")
    print("All eight positions observed:", data["all_eight_positions_observed"])
    print("Full firing verification: NO")
    print("Gameplay access enabled: NO")


if __name__ == "__main__":
    main()
