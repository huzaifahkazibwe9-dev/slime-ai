import json
from pathlib import Path

DATA = Path("data")
ORDER = ["bottom", "right", "top", "left"]

def read(name):
    return json.loads((DATA / name).read_text())

def main():
    calibration = read("conveyor_calibration.json")
    visual = read("conveyor_visual_observations.json")
    detection = read("shooter_detection.json")

    observations = visual["observations"]
    positions = {p["id"]: p for p in calibration["shooters"]}
    shooters = {s["id"]: s for s in detection["visible_shooters"]}

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
        "tracks": {},
        "checks": {},
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
        ),
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
