"""Create an advisory ammunition timeline without assigning shooter identity."""
import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path

DATA = Path("data")
INPUT = DATA / "conveyor_visual_observations.json"
OUTPUT = DATA / "conveyor_timeline.json"

ORDER = ["bottom", "right", "top", "left"]
WHITE_POSITIONS = ["bottom_1", "right_2", "top_2", "left_1"]
BLUE_POSITIONS = ["bottom_2", "right_1", "top_1", "left_2"]


def read_visual_snapshot(path=INPUT):
    raw = Path(path).read_bytes()
    try:
        visual = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Conveyor observations are not valid UTF-8 JSON") from exc
    if not isinstance(visual, dict):
        raise ValueError("Conveyor observations must be a JSON object")
    return visual, hashlib.sha256(raw).hexdigest()


def build_timeline_report(visual, visual_sha256=None):
    """Build position-based ammo trends; never infer physical shooter identity."""
    if not isinstance(visual, dict):
        raise ValueError("Conveyor observations must be a JSON object")
    raw_observations = visual.get("observations")
    if not isinstance(raw_observations, list):
        raise ValueError("Conveyor observations must contain an observations list")

    observations = {}
    for index, item in enumerate(raw_observations):
        if not isinstance(item, dict):
            raise ValueError(f"Observation {index} must be an object")
        position_id = item.get("position_id")
        if not isinstance(position_id, str) or not position_id:
            raise ValueError(f"Observation {index} has an invalid position_id")
        if position_id in observations:
            raise ValueError(f"Duplicate conveyor position: {position_id}")
        ammo = item.get("ammo")
        if type(ammo) is not int or ammo < 0:
            raise ValueError(f"Observation {index} has invalid ammunition")
        colour = item.get("colour")
        if not isinstance(colour, str) or not colour:
            raise ValueError(f"Observation {index} has an invalid colour")
        observations[position_id] = item

    required_positions = set(WHITE_POSITIONS + BLUE_POSITIONS)
    if set(observations) != required_positions:
        missing = sorted(required_positions - set(observations))
        extra = sorted(set(observations) - required_positions)
        raise ValueError(
            f"Conveyor positions do not match the expected layout; "
            f"missing={missing}, extra={extra}"
        )

    timeline = []
    for index, side in enumerate(ORDER):
        white_id = WHITE_POSITIONS[index]
        blue_id = BLUE_POSITIONS[index]
        timeline.append({
            "sequence": index + 1,
            "side": side,
            "white_position_observation": observations[white_id],
            "blue_cyan_position_observation": observations[blue_id],
        })

    white_ammo = [
        step["white_position_observation"]["ammo"] for step in timeline
    ]
    blue_ammo = [
        step["blue_cyan_position_observation"]["ammo"] for step in timeline
    ]
    captured_at = visual.get("captured_at")
    timestamp_identified = False
    if isinstance(captured_at, str) and captured_at:
        try:
            parsed = datetime.fromisoformat(captured_at.replace("Z", "+00:00"))
            timestamp_identified = (
                parsed.tzinfo is not None and parsed.utcoffset() is not None
                and visual.get("timestamp_identified") is True
            )
        except ValueError:
            timestamp_identified = False

    return {
        "sequence": ORDER,
        "sequence_confirmed_by_user": (
            visual.get("sequence_confirmed_by_user") is True
        ),
        "board_snapshot_id": visual.get("board_snapshot_id"),
        "capture_session_id": visual.get("capture_session_id"),
        "captured_at": captured_at,
        "timestamps_known": timestamp_identified,
        "same_board_state_confirmed": (
            visual.get("same_board_state_confirmed") is True
        ),
        "identity_verified": False,
        "candidate_tracks": {
            "white_position_series": {
                "candidate_shooter": None,
                "identity_status": "UNRESOLVED",
                "ammo": white_ammo,
                "non_increasing": all(
                    later <= earlier
                    for earlier, later in zip(white_ammo, white_ammo[1:])
                ),
            },
            "blue_cyan_position_series": {
                "candidate_shooter": None,
                "identity_status": "UNRESOLVED",
                "ammo": blue_ammo,
                "non_increasing": all(
                    later <= earlier
                    for earlier, later in zip(blue_ammo, blue_ammo[1:])
                ),
            },
        },
        "snapshots": timeline,
        "source_file_sha256": visual_sha256,
        "interpretation": (
            "Position-based ammunition trend only. This report does not "
            "identify which physical shooter occupies a position. Use the "
            "human-confirmed identity audit and conveyor identity matcher "
            "for identity candidates."
        ),
        "gameplay_verified": False,
        "gameplay_taps_enabled": False,
        "game_taps_enabled": False,
        "actions_performed": False,
    }


def main(input_path=INPUT, output_path=OUTPUT):
    try:
        visual, digest = read_visual_snapshot(input_path)
        report = build_timeline_report(visual, digest)
    except (OSError, ValueError) as exc:
        report = {
            "sequence": ORDER,
            "sequence_confirmed_by_user": False,
            "timestamps_known": False,
            "identity_verified": False,
            "candidate_tracks": {},
            "snapshots": [],
            "source_file_sha256": None,
            "input_error": f"{type(exc).__name__}: {exc}",
            "gameplay_verified": False,
            "gameplay_taps_enabled": False,
            "game_taps_enabled": False,
            "actions_performed": False,
            "interpretation": "Timeline unavailable; no shooter identity inferred.",
        }
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(output_path.suffix + ".tmp")
    temporary.write_text(json.dumps(report, indent=2), encoding="utf-8")
    temporary.replace(output_path)

    print("SLIME AI — POSITION-BASED CONVEYOR TIMELINE")
    print("=" * 48)
    print("Sequence confirmed by user:", report["sequence_confirmed_by_user"])
    print("Timestamps known:", report["timestamps_known"])
    print("Physical identity verified:", report["identity_verified"])
    print("Game taps enabled:", report["game_taps_enabled"])
    if "input_error" in report:
        print("Input error:", report["input_error"])
    print("Report:", output_path)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Build a non-identity conveyor ammunition timeline"
    )
    parser.add_argument("--input", default=str(INPUT))
    parser.add_argument("--output", default=str(OUTPUT))
    args = parser.parse_args()
    main(Path(args.input), Path(args.output))
