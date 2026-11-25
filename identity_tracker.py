"""Read-only, frame-specific shooter identity observations."""

import json
from strict_json import strict_json_loads
from pathlib import Path

DETECTION_FILE = Path("data/shooter_detection.json")
CALIBRATION_FILE = Path("data/conveyor_calibration.json")
IDENTITY_FILE = Path("data/shooter_identity_observations.json")


def load_reference_data():
    detection = strict_json_loads(DETECTION_FILE.read_text())
    calibration = strict_json_loads(CALIBRATION_FILE.read_text())

    shooters = {
        item["id"]: item
        for item in detection["visible_shooters"]
    }

    positions = {
        item["id"]: item
        for item in calibration["shooters"]
    }

    return shooters, positions


def validate_observations(observations, shooters=None, positions=None):
    if shooters is None or positions is None:
        shooters, positions = load_reference_data()

    errors = []
    frames = {}

    for index, observation in enumerate(observations):
        frame_id = observation.get("frame_id")
        position_id = observation.get("position_id")
        shooter_id = observation.get("shooter_id")

        if not frame_id:
            errors.append(f"Observation {index}: missing frame_id")
            continue

        if position_id not in positions:
            errors.append(
                f"Observation {index}: unknown position {position_id}"
            )
            continue

        if shooter_id not in shooters:
            errors.append(
                f"Observation {index}: unknown shooter {shooter_id}"
            )
            continue

        frame = frames.setdefault(
            frame_id,
            {"positions": set(), "shooters": set()},
        )

        if position_id in frame["positions"]:
            errors.append(
                f"Frame {frame_id}: duplicate position {position_id}"
            )

        if shooter_id in frame["shooters"]:
            errors.append(
                f"Frame {frame_id}: duplicate shooter {shooter_id}"
            )

        frame["positions"].add(position_id)
        frame["shooters"].add(shooter_id)

        if observation.get("verified") is not True:
            errors.append(
                f"Frame {frame_id}: unverified identity "
                f"{position_id} -> {shooter_id}"
            )

    return errors


def run_tests():
    shooters, positions = load_reference_data()

    sample = [
        {
            "frame_id": "test_frame_1",
            "position_id": "bottom_1",
            "shooter_id": "top_1",
            "verified": True,
        },
        {
            "frame_id": "test_frame_2",
            "position_id": "right_1",
            "shooter_id": "top_1",
            "verified": True,
        },
    ]

    assert validate_observations(sample, shooters, positions) == []
    print("[PASS] Same shooter can appear in different frames")

    duplicate_position = sample + [{
        "frame_id": "test_frame_1",
        "position_id": "bottom_1",
        "shooter_id": "top_2",
        "verified": True,
    }]

    assert any(
        "duplicate position" in error
        for error in validate_observations(
            duplicate_position, shooters, positions
        )
    )
    print("[PASS] Duplicate position within a frame rejected")

    duplicate_shooter = sample + [{
        "frame_id": "test_frame_1",
        "position_id": "bottom_2",
        "shooter_id": "top_1",
        "verified": True,
    }]

    assert any(
        "duplicate shooter" in error
        for error in validate_observations(
            duplicate_shooter, shooters, positions
        )
    )
    print("[PASS] Duplicate shooter within a frame rejected")

    unverified = [{
        "frame_id": "test_frame_3",
        "position_id": "top_1",
        "shooter_id": "top_2",
        "verified": False,
    }]

    assert any(
        "unverified identity" in error
        for error in validate_observations(
            unverified, shooters, positions
        )
    )
    print("[PASS] Unverified identity rejected")

    print("4/4 identity tracker tests passed.")
    print("Synthetic test data was not saved.")


def report():
    shooters, positions = load_reference_data()

    if IDENTITY_FILE.exists():
        data = strict_json_loads(IDENTITY_FILE.read_text())
        observations = data.get("observations", [])
    else:
        observations = []

    visual_file = Path("data/conveyor_visual_observations.json")
    visual = (
        strict_json_loads(visual_file.read_text())
        if visual_file.exists() else {"observations": []}
    )
    visual_observations = visual.get("observations", [])

    errors = validate_observations(observations, shooters, positions)

    visual_ids = [x.get("position_id") for x in visual_observations]
    visual_valid = (
        len(visual_ids) == 8
        and len(set(visual_ids)) == 8
        and set(visual_ids) == set(positions)
        and all(
            x.get("colour") in ("white", "blue")
            and isinstance(x.get("ammo"), int)
            and x["ammo"] >= 0
            for x in visual_observations
        )
    )

    print("\\nSLIME AI — INTEGRATED IDENTITY TRACKER")
    print("=" * 48)
    print("Detected shooters:", len(shooters))
    print("Calibrated positions:", len(positions))
    print("Verified identity records:", len(observations))
    print("Visual observations:", len(visual_observations))

    print("\\nVISUAL OBSERVATIONS")
    for item in visual_observations:
        print(
            item.get("position_id"),
            "|", item.get("colour"),
            "| ammo:", item.get("ammo")
        )

    print("\\nIdentity record validation:",
          "PASS" if not errors else "FAIL")
    print("Visual position validation:",
          "PASS" if visual_valid else "FAIL")
    print("Physical identities verified: NO")
    print("Gameplay taps enabled: NO")
    print("No game actions performed.")

    if errors:
        for error in errors:
            print("ERROR:", error)


if __name__ == "__main__":
    run_tests()
    report()
