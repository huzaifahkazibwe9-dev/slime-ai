import json
import re
from datetime import datetime
from pathlib import Path

from capture_provenance import validate_capture_session_id

DATA = Path("data")
ORDER = ["bottom", "right", "top", "left"]

def read(name):
    return json.loads((DATA / name).read_text())


def validate_visual_observations(observations, expected_positions):
    """Reject incomplete or ambiguous frame data before building tracks."""
    if not isinstance(observations, list):
        return ["Observations must be a list"]

    expected = set(expected_positions)
    seen = set()
    errors = []

    if len(observations) != len(expected):
        errors.append(
            f"Expected {len(expected)} observations; got {len(observations)}"
        )

    for index, item in enumerate(observations):
        if not isinstance(item, dict):
            errors.append(f"Observation {index} must be an object")
            continue

        position_id = item.get("position_id")
        if not isinstance(position_id, str) or not position_id.strip():
            errors.append(f"Observation {index} has invalid position_id")
            continue
        if position_id not in expected:
            errors.append(f"Unexpected position: {position_id}")
        if position_id in seen:
            errors.append(f"Duplicate position: {position_id}")
        seen.add(position_id)

        colour = item.get("colour")
        if not isinstance(colour, str) or colour.lower() not in {
            "white", "blue", "cyan"
        }:
            errors.append(f"{position_id}: invalid colour")

        ammo = item.get("ammo")
        if type(ammo) is not int or ammo < 0:
            errors.append(f"{position_id}: invalid ammunition")

    missing = sorted(expected - seen)
    if missing:
        errors.append("Missing positions: " + ", ".join(missing))
    return errors


def validate_visual_provenance(visual):
    """Require explicit identity-frame linkage to a board capture session."""
    if not isinstance(visual, dict):
        return ["Visual observation artifact must be an object"]
    errors = []
    snapshot_id = visual.get("board_snapshot_id")
    if not isinstance(snapshot_id, str) or not re.fullmatch(
        r"sha256:[0-9a-f]{64}", snapshot_id
    ):
        errors.append("Missing or invalid board_snapshot_id")
    try:
        validate_capture_session_id(visual.get("capture_session_id"))
    except ValueError:
        errors.append("Missing or invalid capture_session_id")
    if visual.get("capture_session_id") is None:
        errors.append("Missing or invalid capture_session_id")
    captured_at = visual.get("captured_at")
    if not isinstance(captured_at, str) or not captured_at.strip():
        errors.append("Missing capture timestamp")
    else:
        try:
            parsed = datetime.fromisoformat(captured_at.replace("Z", "+00:00"))
            if parsed.tzinfo is None or parsed.utcoffset() is None:
                errors.append("Capture timestamp must include a UTC offset")
        except ValueError:
            errors.append("Capture timestamp is invalid")
    if visual.get("timestamp_identified") is not True:
        errors.append("Capture timestamp is not explicitly identified")
    return errors


def main():
    calibration = read("conveyor_calibration.json")
    visual = read("conveyor_visual_observations.json")
    detection = read("shooter_detection.json")

    observations = visual["observations"]
    positions = {p["id"]: p for p in calibration["shooters"]}
    shooters = {s["id"]: s for s in detection["visible_shooters"]}

    validation_errors = validate_visual_observations(
        observations, positions
    )
    validation_errors.extend(validate_visual_provenance(visual))
    if validation_errors:
        report = {
            "screenshot_order": ORDER,
            "board_snapshot_id": visual.get("board_snapshot_id"),
            "capture_session_id": visual.get("capture_session_id"),
            "captured_at": visual.get("captured_at"),
            "timestamp_identified": visual.get("timestamp_identified") is True,
            "observations_valid": False,
            "validation_errors": validation_errors,
            "tracks": {},
            "checks": {"observations_valid": False},
            "identity_verified": False,
            "gameplay_taps_enabled": False,
            "note": "Invalid observations rejected; candidate matching skipped.",
        }
        output = DATA / "conveyor_identity_candidates.json"
        output.write_text(json.dumps(report, indent=2))
        print("Observation validation failed:")
        for error in validation_errors:
            print("-", error)
        print("Candidate report:", output)
        print("Identity verified: False")
        print("Gameplay taps enabled: False")
        return report

    by_position = {
        item["position_id"]: item for item in observations
    }

    tracks = {
        "white": {
            "candidate_shooter": "top_1",
            "positions": [
                "bottom_1", "right_2", "top_2", "left_1"
            ],
        },
        "blue_cyan": {
            "candidate_shooter": "top_2",
            "positions": [
                "bottom_2", "right_1", "top_1", "left_2"
            ],
        },
    }

    report = {
        "screenshot_order": ORDER,
        "board_snapshot_id": visual.get("board_snapshot_id"),
        "capture_session_id": visual.get("capture_session_id"),
        "captured_at": visual.get("captured_at"),
        "timestamp_identified": visual.get("timestamp_identified") is True,
        "tracks": {},
        "checks": {"observations_valid": True},
        "identity_verified": False,
        "gameplay_taps_enabled": False,
        "note": "Candidate tracking only; no gameplay identity verification."
    }

    for name, track in tracks.items():
        shooter_id = track["candidate_shooter"]
        shooter = shooters[shooter_id]
        records = []

        for position_id in track["positions"]:
            observation = by_position[position_id]
            position = positions[position_id]
            records.append({
                "position_id": position_id,
                "segment": position["segment"],
                "colour": observation["colour"],
                "ammo": observation["ammo"],
                "center": position["center"],
            })

        ammo = [r["ammo"] for r in records]
        non_increasing = all(
            later <= earlier
            for earlier, later in zip(ammo, ammo[1:])
        )

        expected_colour = (
            "white" if name == "white" else "cyan"
        )

        colour_match = (
            shooter["color"]["name"] == expected_colour
        )

        observed_colours_match = all(
            (
                r["colour"].lower() == "white"
                if name == "white"
                else r["colour"].lower() in {"blue", "cyan"}
            )
            for r in records
        )

        report["tracks"][name] = {
            "candidate_shooter": shooter_id,
            "panel_colour": shooter["color"]["name"],
            "observations": records,
            "ammo_non_increasing": non_increasing,
            "panel_colour_match": colour_match,
            "observed_colour_consistent": observed_colours_match,
            "candidate_supported": (
                non_increasing
                and colour_match
                and observed_colours_match
            ),
        }

    group = set(shooters["top_1"].get("bonded_ids", []))
    observed_order = [
        by_position[f"{side}_1"]["position_id"].split("_")[0]
        for side in ORDER
    ]

    report["checks"] = {
        "four_sides_in_expected_order": (
            observed_order == ORDER
        ),
        "eight_observations_present": len(observations) == 8,
        "two_candidate_tracks_supported": all(
            t["candidate_supported"]
            for t in report["tracks"].values()
        ),
        "candidate_pair_is_user_confirmed_bond": (
            group == {"top_2"}
            and "top_1" in shooters["top_2"].get("bonded_ids", [])
        ),
        "timestamps_known": (
            visual.get("timestamp_identified") is True
            and bool(visual.get("captured_at"))
        ),
        "snapshot_linked": bool(visual.get("board_snapshot_id")),
        "capture_session_linked": bool(visual.get("capture_session_id")),
        "identity_previously_verified": (
            visual.get("identity_verified") is True
        ),
    }

    report["candidate_pair"] = ["top_1", "top_2"]
    report["identity_verified"] = False

    output = DATA / "conveyor_identity_candidates.json"
    output.write_text(json.dumps(report, indent=2))

    print("=" * 52)
    print("SLIME AI — CONVEYOR IDENTITY MATCHER")
    print("=" * 52)

    for name, track in report["tracks"].items():
        print(f"\n{name.upper()} TRACK")
        print("Candidate:", track["candidate_shooter"])
        print("Ammo:", [
            r["ammo"] for r in track["observations"]
        ])
        print("Candidate supported:", track["candidate_supported"])

    print("\nCHECKS")
    for name, passed in report["checks"].items():
        print(f"[{'PASS' if passed else 'PENDING'}] {name}")

    print("\nIdentity verified:", report["identity_verified"])
    print("Gameplay taps enabled:", report["gameplay_taps_enabled"])
    print("Report:", output)
    print("No game actions performed.")

if __name__ == "__main__":
    main()
