#!/usr/bin/env python3

import argparse
import copy
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "data" / "vision_level39.json"
OUTPUT = ROOT / "data" / "firing_simulation_latest.json"

DIRECTIONS = {
    "top_down": (1, 0),
    "bottom_up": (-1, 0),
    "left_right": (0, 1),
    "right_left": (0, -1),
}


def validate_board(board):
    if not isinstance(board, list) or len(board) != 35:
        raise ValueError("Board must contain exactly 35 rows.")

    for row in board:
        if not isinstance(row, list) or len(row) != 35:
            raise ValueError("Every board row must contain 35 cells.")

    if any(not isinstance(cell, str) for row in board for cell in row):
        raise ValueError("Every board cell must contain a colour string.")


def simulate(board, direction, lane, colour, ammo):
    validate_board(board)

    if direction not in DIRECTIONS:
        raise ValueError(f"Unknown direction: {direction}")

    if not isinstance(lane, int) or not 0 <= lane < 35:
        raise ValueError("Lane must be an integer from 0 to 34.")

    if not isinstance(ammo, int) or ammo < 0:
        raise ValueError("Ammo must be a non-negative integer.")

    if not isinstance(colour, str) or not colour:
        raise ValueError("Shooter colour must be a non-empty string.")

    # Work only on a private copy.
    working = copy.deepcopy(board)

    dr, dc = DIRECTIONS[direction]

    if direction in ("top_down", "bottom_up"):
        r = 0 if dr == 1 else 34
        c = lane
    else:
        r = lane
        c = 0 if dc == 1 else 34

    shots_used = 0
    removed = []
    status = "AMMO_EXHAUSTED"

    while 0 <= r < 35 and 0 <= c < 35:
        if shots_used >= ammo:
            status = "AMMO_EXHAUSTED"
            break

        target_colour = working[r][c]

        if target_colour != colour:
            status = "BLOCKED_BY_DIFFERENT_COLOUR"
            break

        removed.append({
            "cell": [r, c],
            "colour": target_colour,
        })

        working[r][c] = None
        shots_used += 1

        r += dr
        c += dc

    else:
        status = "LANE_CLEARED"

    return {
        "direction": direction,
        "lane": lane,
        "shooter_colour": colour,
        "initial_ammo": ammo,
        "shots_used": shots_used,
        "remaining_ammo": ammo - shots_used,
        "removed_count": len(removed),
        "removed_cells": removed,
        "status": status,
        "next_cell": [r, c] if 0 <= r < 35 and 0 <= c < 35 else None,
        "next_cell_colour": (
            working[r][c] if 0 <= r < 35 and 0 <= c < 35 else None
        ),
        "simulated_board": working,
    }


def run_tests():
    print("RUNNING FIRING SIMULATOR TESTS")
    print("=" * 45)

    tests = []

    def check(name, condition):
        tests.append((name, bool(condition)))

    board = [["cyan"] * 35 for _ in range(35)]

    result = simulate(board, "top_down", 4, "cyan", 10)
    check(
        "Matching cells are removed",
        result["removed_count"] == 10
        and result["shots_used"] == 10
        and result["remaining_ammo"] == 0
    )

    board = [["cyan"] * 35 for _ in range(35)]
    board[3][4] = "white"

    result = simulate(board, "top_down", 4, "cyan", 10)
    check(
        "Different colour blocks firing",
        result["removed_count"] == 3
        and result["status"] == "BLOCKED_BY_DIFFERENT_COLOUR"
        and result["next_cell_colour"] == "white"
    )

    board = [["cyan"] * 35 for _ in range(35)]
    result = simulate(board, "bottom_up", 2, "cyan", 2)
    check(
        "Bottom shooter fires upward",
        result["removed_cells"] == [
            {"cell": [34, 2], "colour": "cyan"},
            {"cell": [33, 2], "colour": "cyan"},
        ]
    )

    board = [["cyan"] * 35 for _ in range(35)]
    result = simulate(board, "left_right", 7, "cyan", 3)
    check(
        "Left shooter fires rightward",
        result["removed_cells"] == [
            {"cell": [7, 0], "colour": "cyan"},
            {"cell": [7, 1], "colour": "cyan"},
            {"cell": [7, 2], "colour": "cyan"},
        ]
    )

    board = [["cyan"] * 35 for _ in range(35)]
    result = simulate(board, "right_left", 8, "cyan", 2)
    check(
        "Right shooter fires leftward",
        result["removed_cells"] == [
            {"cell": [8, 34], "colour": "cyan"},
            {"cell": [8, 33], "colour": "cyan"},
        ]
    )

    board = [["cyan"] * 35 for _ in range(35)]
    original = copy.deepcopy(board)
    simulate(board, "top_down", 0, "cyan", 5)
    check(
        "Original board remains unchanged",
        board == original
    )

    board = [["cyan"] * 35 for _ in range(35)]
    result = simulate(board, "top_down", 0, "cyan", 40)
    check(
        "Firing stops at board boundary",
        result["removed_count"] == 35
        and result["status"] == "LANE_CLEARED"
    )

    passed = 0

    for name, success in tests:
        print(f"[{'PASS' if success else 'FAIL'}] {name}")
        passed += int(success)

    print(f"\nTests passed: {passed}/{len(tests)}")

    if passed != len(tests):
        raise RuntimeError("Simulator tests failed.")

    print("All simulator tests passed.")


def main():
    parser = argparse.ArgumentParser(
        description="Read-only Slime Loop firing simulator"
    )

    parser.add_argument(
        "--direction",
        choices=sorted(DIRECTIONS),
        help="Firing direction"
    )
    parser.add_argument(
        "--lane",
        type=int,
        help="Lane number from 0 to 34"
    )
    parser.add_argument(
        "--colour",
        help="Hypothetical shooter colour"
    )
    parser.add_argument(
        "--ammo",
        type=int,
        help="Shooter ammunition"
    )

    args = parser.parse_args()

    run_tests()

    if not SOURCE.exists():
        raise FileNotFoundError(SOURCE)

    data = json.loads(SOURCE.read_text())
    original_board = data["board"]
    validate_board(original_board)

    if args.direction is None:
        print("\nNo simulation parameters supplied.")
        print("Running a sample analysis using the Level 39 board.")
        direction = "top_down"
        lane = 0
        colour = "cyan"
        ammo = 40
    else:
        if (
            args.lane is None
            or args.colour is None
            or args.ammo is None
        ):
            parser.error(
                "--direction requires --lane, --colour and --ammo"
            )

        direction = args.direction
        lane = args.lane
        colour = args.colour
        ammo = args.ammo

    result = simulate(
        original_board,
        direction,
        lane,
        colour,
        ammo
    )

    # Do not save the copied board: save only the simulation report.
    report = {
        "version": 1,
        "source": "vision_level39.json",
        "gameplay_verified": False,
        "colour_mapping_verified": False,
        "simulation": {
            key: value
            for key, value in result.items()
            if key != "simulated_board"
        },
        "original_board_unchanged": True,
        "gameplay_actions_performed": False,
    }

    OUTPUT.write_text(json.dumps(report, indent=2))

    print("\nSLIME AI — FIRING SIMULATION")
    print("=" * 45)
    print("Direction:", direction)
    print("Lane:", lane)
    print("Shooter colour:", colour)
    print("Initial ammunition:", ammo)
    print("Shots used:", result["shots_used"])
    print("Remaining ammunition:", result["remaining_ammo"])
    print("Pixels removed:", result["removed_count"])
    print("Status:", result["status"])
    print("Next cell:", result["next_cell"])
    print("Next cell colour:", result["next_cell_colour"])
    print("Removed cells:", result["removed_cells"][:12])
    print("Report saved:", OUTPUT)
    print("Original board modified: NO")
    print("Gameplay actions performed: NO")


if __name__ == "__main__":
    main()
