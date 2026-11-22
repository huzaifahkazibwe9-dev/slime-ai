import json
from pathlib import Path

DATA = Path("data")

ORDER = ["bottom", "right", "top", "left"]

WHITE_POSITIONS = [
    "bottom_1", "right_2", "top_2", "left_1"
]

BLUE_POSITIONS = [
    "bottom_2", "right_1", "top_1", "left_2"
]

def main():
    visual = json.loads(
        (DATA / "conveyor_visual_observations.json").read_text()
    )

    observations = {
        item["position_id"]: item
        for item in visual["observations"]
    }

    timeline = []

    for index, side in enumerate(ORDER):
        white_id = WHITE_POSITIONS[index]
        blue_id = BLUE_POSITIONS[index]

        if white_id not in observations or blue_id not in observations:
            raise ValueError(f"Missing observation at {side}")

        timeline.append({
            "sequence": index + 1,
            "side": side,
            "white_candidate": observations[white_id],
            "blue_cyan_candidate": observations[blue_id],
        })

    white_ammo = [
        step["white_candidate"]["ammo"]
        for step in timeline
    ]

    blue_ammo = [
        step["blue_cyan_candidate"]["ammo"]
        for step in timeline
    ]

    report = {
        "sequence": ORDER,
        "sequence_confirmed_by_user": True,
        "timestamps_known": False,
        "identity_verified": False,
        "gameplay_taps_enabled": False,
        "candidate_tracks": {
            "white": {
                "candidate_shooter": "top_1",
                "ammo": white_ammo,
                "non_increasing": all(
                    b <= a for a, b in zip(
                        white_ammo, white_ammo[1:]
                    )
                ),
            },
            "blue_cyan": {
                "candidate_shooter": "top_2",
                "ammo": blue_ammo,
                "non_increasing": all(
                    b <= a for a, b in zip(
                        blue_ammo, blue_ammo[1:]
                    )
                ),
            },
        },
        "snapshots": timeline,
    }

    output = DATA / "conveyor_timeline.json"
    output.write_text(json.dumps(report, indent=2))

    print("SLIME AI — CONVEYOR TIMELINE")
    print("=" * 42)

    for step in timeline:
        print(
            f'{step["sequence"]}. {step["side"].upper():6} '
            f'white={step["white_candidate"]["ammo"]:2} '
            f'blue/cyan={step["blue_cyan_candidate"]["ammo"]:2}'
        )

    print("\nWhite ammunition:", white_ammo)
    print("Blue/cyan ammunition:", blue_ammo)
    print("Sequence confirmed by user: True")
    print("Timestamps known: False")
    print("Identity verified: False")
    print("Gameplay taps enabled: False")
    print("Report:", output)

if __name__ == "__main__":
    main()
