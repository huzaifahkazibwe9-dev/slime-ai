import argparse
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


def build_timeline(visual, *, sequence_confirmed_by_user=False):
    """Assemble a four-stage candidate timeline from visual observations.

    This is a structural rearrangement only. It does not verify shooter
    identity, timestamps, or gameplay. ``sequence_confirmed_by_user`` is
    recorded only when the caller explicitly says the operator confirmed
    the stage order; screenshots never imply that confirmation.
    """
    if not isinstance(visual, dict):
        raise ValueError("Visual observations must be a JSON object")

    observations_list = visual.get("observations")
    if not isinstance(observations_list, list):
        raise ValueError("Visual observations are missing an observations list")

    observations = {}
    for item in observations_list:
        if not isinstance(item, dict) or not item.get("position_id"):
            raise ValueError("Each observation needs a position_id")
        observations[item["position_id"]] = item

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

    return {
        "sequence": list(ORDER),
        "sequence_confirmed_by_user": bool(sequence_confirmed_by_user),
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


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            "Build a candidate conveyor timeline. "
            "Does not verify identity or enable gameplay taps."
        )
    )
    parser.add_argument(
        "--observations",
        default=str(DATA / "conveyor_visual_observations.json"),
        help="Passive conveyor visual observations JSON",
    )
    parser.add_argument(
        "--output",
        default=str(DATA / "conveyor_timeline.json"),
        help="Where to write the candidate timeline JSON",
    )
    parser.add_argument(
        "--confirm-sequence",
        action="store_true",
        help=(
            "Record that the operator explicitly confirmed the stage order. "
            "Never inferred from screenshots."
        ),
    )
    args = parser.parse_args(argv)

    visual = json.loads(Path(args.observations).read_text())
    report = build_timeline(
        visual,
        sequence_confirmed_by_user=args.confirm_sequence,
    )

    output = Path(args.output)
    output.write_text(json.dumps(report, indent=2))

    print("SLIME AI — CONVEYOR TIMELINE")
    print("=" * 42)

    for step in report["snapshots"]:
        print(
            f'{step["sequence"]}. {step["side"].upper():6} '
            f'white={step["white_candidate"]["ammo"]:2} '
            f'blue/cyan={step["blue_cyan_candidate"]["ammo"]:2}'
        )

    print("\nWhite ammunition:", report["candidate_tracks"]["white"]["ammo"])
    print("Blue/cyan ammunition:", report["candidate_tracks"]["blue_cyan"]["ammo"])
    print(
        "Sequence confirmed by user:",
        report["sequence_confirmed_by_user"],
    )
    print("Timestamps known: False")
    print("Identity verified: False")
    print("Gameplay taps enabled: False")
    print("Report:", output)
    return report


if __name__ == "__main__":
    main()
