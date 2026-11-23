import argparse
import json
from pathlib import Path
from collections import Counter

from conveyor_geometry import calculate_firing_geometry

CALIBRATION_FILE = Path("data/conveyor_calibration.json")
OBSERVATIONS_FILE = Path("data/conveyor_visual_observations.json")
BOARD_FILE = Path("data/vision_level39.json")
OUTPUT_FILE = Path("data/reachability_audit.json")

# These are alternative visual interpretations, not verified mappings.
COLOUR_CANDIDATES = {
    "white": ["white"],
    "blue": ["blue", "cyan"],
}


def trace_lane(board, first_cell, direction, target_colour):
    height = len(board)
    width = len(board[0]) if height else 0

    if not board or any(len(row) != width for row in board):
        raise ValueError("Board must be a non-empty rectangular grid")

    x, y = first_cell

    if not (0 <= x < width and 0 <= y < height):
        raise ValueError(f"First cell outside board: {first_cell}")

    vectors = {
        "up": (0, -1),
        "down": (0, 1),
        "left": (-1, 0),
        "right": (1, 0),
    }

    if direction not in vectors:
        raise ValueError(f"Invalid direction: {direction}")

    dx, dy = vectors[direction]
    cells = []
    matching_run = []
    blocker = None
    matches_behind_blocker = []

    while 0 <= x < width and 0 <= y < height:
        colour = board[y][x]
        cell = {
            "row": y,
            "column": x,
            "colour": colour,
        }
        cells.append(cell)

        if blocker is None:
            if colour == target_colour:
                matching_run.append(cell)
            else:
                blocker = cell
        elif colour == target_colour:
            matches_behind_blocker.append(cell)

        x += dx
        y += dy

    if blocker is None:
        status = (
            "EXPOSED_MATCHING_RUN"
            if matching_run else "NO_MATCHING_TILES"
        )
    elif not matching_run:
        status = "BLOCKED_BY_DIFFERENT_COLOUR"
    else:
        status = "MATCHING_RUN_THEN_BLOCKED"

    return {
        "status": status,
        "target_colour": target_colour,
        "first_cell": first_cell,
        "first_cell_colour": cells[0]["colour"],
        "lane_length": len(cells),
        "exposed_matching_count": len(matching_run),
        "exposed_matching_cells": matching_run,
        "first_blocker": blocker,
        "matching_tiles_behind_blocker_count":
            len(matches_behind_blocker),
        "matching_tiles_behind_blocker":
            matches_behind_blocker,
        "lane_cells": cells,
    }


def _audit_core(board_data, calibration, observations):
    board = board_data["board"]
    height = len(board)
    width = len(board[0]) if height else 0

    if not board or any(len(row) != width for row in board):
        raise ValueError("Invalid board dimensions")

    if not calibration.get("verified_by_user"):
        raise ValueError("Conveyor calibration is not user-verified")

    image_size = tuple(calibration["image_size"])
    observation_lookup = {
        item["position_id"]: item
        for item in observations.get("observations", [])
    }

    results = []

    for position in calibration["shooters"]:
        position_id = position["id"]
        segment = position["segment"]
        observation = observation_lookup.get(position_id)

        geometry = calculate_firing_geometry(
            screen_center=position["center"],
            segment=segment,
            image_size=image_size,
            position_verified=True,
        )

        first_cell = geometry["first_board_cell"]

        x, y = first_cell
        if not (0 <= x < width and 0 <= y < height):
            raise ValueError(
                f"Invalid first cell for {position_id}: {first_cell}"
            )

        if observation is None:
            results.append({
                "position_id": position_id,
                "direction": geometry["direction"],
                "first_cell": first_cell,
                "status": "NO_VISUAL_OBSERVATION",
                "scenarios": [],
            })
            continue

        observed_colour = observation["colour"]
        candidates = COLOUR_CANDIDATES.get(
            observed_colour, [observed_colour]
        )

        scenarios = []

        for candidate in candidates:
            lane = trace_lane(
                board,
                first_cell,
                geometry["direction"],
                candidate,
            )
            scenarios.append(lane)

        results.append({
            "position_id": position_id,
            "direction": geometry["direction"],
            "first_cell": first_cell,
            "observed_colour": observed_colour,
            "observed_ammo": observation["ammo"],
            "identity_verified": False,
            "candidate_board_colours": candidates,
            "scenarios": scenarios,
        })

    return {
        "level": 39,
        "board_dimensions": [width, height],
        "calibration_verified_by_user":
            calibration["verified_by_user"],
        "conveyor_identity_verified":
            observations.get("identity_verified", False),
        "observation_timestamps_identified":
            observations.get("timestamp_identified", False),
        "gameplay_verified": False,
        "game_taps_enabled": False,
        "method": (
            "Read-only straight-line lane tracing. "
            "Matching cells remain exposed only until the first "
            "different-colour tile."
        ),
        "results": results,
        "warning": (
            "Visual observations do not establish shooter identity "
            "or gameplay colour equivalence. Candidate colour "
            "scenarios are alternatives, not verified mappings."
        ),
    }



def audit(board_data, calibration, observations):
    """Add strict temporal and ammunition eligibility checks."""
    report = _audit_core(board_data, calibration, observations)

    board_id = board_data.get("snapshot_id")
    observation_board_id = observations.get("board_snapshot_id")

    timestamps_known = (
        board_data.get("timestamp_identified", False)
        and observations.get("timestamp_identified", False)
    )

    same_state = (
        timestamps_known
        and bool(board_id)
        and board_id == observation_board_id
        and observations.get("same_board_state_confirmed", False)
    )

    identity_verified = (
        observations.get("identity_verified", False)
    )
    gameplay_verified = (
        observations.get("gameplay_verified", False)
    )

    report["board_timestamp_identified"] = timestamps_known
    report["same_board_state_confirmed"] = same_state
    report["planning_eligibility_requires"] = [
        "matching board and observation snapshot",
        "verified shooter identity",
        "gameplay-verified colour mapping",
        "positive ammunition",
    ]

    from ammo_reconciliation import validate_ammo_observation

    observation_lookup = {
        item.get("position_id"): item
        for item in observations.get("observations", [])
        if isinstance(item, dict)
    }

    for position in report["results"]:
        ammo = position.get("observed_ammo")
        ammo_evidence = validate_ammo_observation(
            position.get("position_id"),
            ammo,
            observation_lookup.get(position.get("position_id")),
        )
        position["ammo_evidence"] = ammo_evidence
        ammo_available = type(ammo) is int and ammo > 0

        blockers = []
        if not same_state:
            blockers.append("BOARD_AND_OBSERVATION_TIMING_UNCONFIRMED")
        if not identity_verified:
            blockers.append("SHOOTER_IDENTITY_UNVERIFIED")
        if not gameplay_verified:
            blockers.append("GAMEPLAY_MAPPING_UNVERIFIED")
        if not ammo_available:
            blockers.append("NO_REMAINING_AMMUNITION")
        if not ammo_evidence["verified"]:
            blockers.append("AMMUNITION_OBSERVATION_UNVERIFIED")

        eligible = (
            same_state
            and identity_verified
            and gameplay_verified
            and ammo_available
            and ammo_evidence["verified"]
        )

        position["ammunition_available"] = ammo_available
        position["ammunition_evidence_verified"] = ammo_evidence["verified"]
        position["planning_eligible"] = eligible
        position["planning_blockers"] = blockers

        for scenario in position.get("scenarios", []):
            scenario["planning_eligible"] = eligible

    report["planning_ready_positions"] = sum(
        item["planning_eligible"] for item in report["results"]
    )
    report["game_taps_enabled"] = False

    return report


def main():
    parser = argparse.ArgumentParser(
        description="Read-only shooter-lane reachability analysis"
    )
    parser.add_argument(
        "--board",
        default=str(BOARD_FILE),
        help="Board JSON; accepts the legacy baseline or screenshot-ingestor observation",
    )
    parser.add_argument(
        "--calibration",
        default=str(CALIBRATION_FILE),
        help="User-confirmed conveyor geometry calibration JSON",
    )
    parser.add_argument(
        "--observations",
        default=str(OBSERVATIONS_FILE),
        help="Passive conveyor visual observations JSON",
    )
    parser.add_argument(
        "--output",
        default=str(OUTPUT_FILE),
        help="Output JSON report",
    )
    args = parser.parse_args()

    board_path = Path(args.board)
    board_data = json.loads(board_path.read_text())
    if "raw_rgb" in board_data:
        # Validate screenshot schema and RGB/label consistency before tracing.
        from screenshot_observation_loader import _require_grid
        _require_grid(board_data)

    calibration = json.loads(Path(args.calibration).read_text())
    observations = json.loads(Path(args.observations).read_text())

    report = audit(board_data, calibration, observations)
    report["board_source"] = str(board_path)
    report["board_snapshot_id"] = board_data.get("snapshot_id")
    report["board_colour_truth_verified"] = False
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2))

    print("SLIME AI — BOARD REACHABILITY AUDITOR")
    print("=" * 48)
    print("Board:", report["board_dimensions"])
    print("Calibrated positions:", len(report["results"]))

    for position in report["results"]:
        print()
        print(
            position["position_id"],
            "| direction:", position["direction"],
            "| first cell:", position["first_cell"],
        )

        if not position["scenarios"]:
            print("  No visual observation")
            continue

        print(
            "  Observed colour:", position["observed_colour"],
            "| ammo:", position["observed_ammo"],
        )

        for scenario in position["scenarios"]:
            print(
                "  Candidate:", scenario["target_colour"],
                "| status:", scenario["status"],
                "| exposed:", scenario["exposed_matching_count"],
                "| blocker:", scenario["first_blocker"],
                "| matches behind blocker:",
                scenario["matching_tiles_behind_blocker_count"],
            )

    print("\nSAFETY STATUS")
    print("Identity verified:", report["conveyor_identity_verified"])
    print("Gameplay verified:", report["gameplay_verified"])
    print("Game taps enabled:", report["game_taps_enabled"])
    print("No game actions performed.")
    print("Board source:", report["board_source"])
    print("Board snapshot:", report["board_snapshot_id"])
    print("Board colour truth verified:", report["board_colour_truth_verified"])
    print("Report:", output_path)


if __name__ == "__main__":
    main()
