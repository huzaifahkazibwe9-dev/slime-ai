#!/usr/bin/env python3
"""
Sequential, read-only Slime Loop firing simulator.

Simulates hypothetical shooters in order on a private evolving board.
Never performs gameplay actions or modifies the source board.
"""

import copy
import json
from strict_json import strict_json_loads
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "data" / "vision_level39.json"
OUTPUT = ROOT / "data" / "sequential_simulation_latest.json"

DIRECTIONS = {
    "top_down": (1, 0),
    "bottom_up": (-1, 0),
    "left_right": (0, 1),
    "right_left": (0, -1),
}


def validate_board(board):
    if not isinstance(board, list) or not board:
        raise ValueError("Board must be a non-empty list.")

    if not isinstance(board[0], list) or not board[0]:
        raise ValueError("Board rows must be non-empty lists.")

    width = len(board[0])

    for row in board:
        if not isinstance(row, list) or len(row) != width:
            raise ValueError("Board must be rectangular.")

        for cell in row:
            if cell is not None and (
                not isinstance(cell, str) or not cell.strip()
            ):
                raise ValueError("Cells must contain colours or None.")

    return len(board), width


def validate_shooter(shooter):
    if not isinstance(shooter, dict):
        raise ValueError("Every shooter must be a dictionary.")

    required = ("direction", "lane", "colour", "ammo")
    missing = [key for key in required if key not in shooter]

    if missing:
        raise ValueError(f"Shooter is missing fields: {missing}")

    direction = shooter["direction"]
    lane = shooter["lane"]
    colour = shooter["colour"]
    ammo = shooter["ammo"]

    if direction not in DIRECTIONS:
        raise ValueError(f"Unsupported direction: {direction}")

    if not isinstance(lane, int) or isinstance(lane, bool):
        raise ValueError("Shooter lane must be an integer.")

    if not isinstance(colour, str) or not colour.strip():
        raise ValueError("Shooter colour must be a non-empty string.")

    if not isinstance(ammo, int) or isinstance(ammo, bool) or ammo < 0:
        raise ValueError("Shooter ammo must be a non-negative integer.")


def simulate_shooter(board, shooter, shooter_index):
    """Apply one hypothetical shooter to an evolving board."""

    validate_shooter(shooter)
    height, width = validate_board(board)

    direction = shooter["direction"]
    lane = shooter["lane"]
    colour = shooter["colour"].strip().lower()
    ammo = shooter["ammo"]

    if direction in ("top_down", "bottom_up"):
        if not 0 <= lane < width:
            raise ValueError(f"Lane must be between 0 and {width - 1}.")

        row = 0 if direction == "top_down" else height - 1
        col = lane

    else:
        if not 0 <= lane < height:
            raise ValueError(f"Lane must be between 0 and {height - 1}.")

        row = lane
        col = 0 if direction == "left_right" else width - 1

    dr, dc = DIRECTIONS[direction]

    shots_used = 0
    removed = []
    status = "LANE_CLEARED"
    next_cell = None
    next_colour = None

    while 0 <= row < height and 0 <= col < width:

        target_colour = board[row][col]

        # Empty cells do not consume ammunition.
        if target_colour is None:
            row += dr
            col += dc
            continue

        # A remaining occupied cell needs a shot.
        if shots_used >= ammo:
            status = "AMMO_EXHAUSTED"
            next_cell = [row, col]
            next_colour = target_colour
            break

        if target_colour.strip().lower() != colour:
            status = "BLOCKED_BY_DIFFERENT_COLOUR"
            next_cell = [row, col]
            next_colour = target_colour
            break

        removed.append({
            "cell": [row, col],
            "colour": target_colour,
        })

        board[row][col] = None
        shots_used += 1

        row += dr
        col += dc

    # If the shooter used its final shot and the path ended,
    # report exhaustion even when the final target was at the boundary.
    if status == "LANE_CLEARED" and ammo > 0 and shots_used == ammo:
        status = "AMMO_EXHAUSTED"

    return {
        "shooter_index": shooter_index,
        "shooter_id": shooter.get("id", f"shooter_{shooter_index}"),
        "direction": direction,
        "lane": lane,
        "colour": shooter["colour"],
        "initial_ammo": ammo,
        "shots_used": shots_used,
        "remaining_ammo": ammo - shots_used,
        "removed_count": len(removed),
        "removed_cells": removed,
        "status": status,
        "next_cell": next_cell,
        "next_cell_colour": next_colour,
    }


def simulate_sequence(original_board, shooters):
    """
    Simulate shooters in the supplied order.

    Each shooter sees the board left by all preceding shooters.
    The caller's original board is never modified.
    """

    validate_board(original_board)

    if not isinstance(shooters, list):
        raise ValueError("Shooters must be supplied as a list.")

    working_board = copy.deepcopy(original_board)
    original_copy = copy.deepcopy(original_board)

    results = []

    for index, shooter in enumerate(shooters, start=1):
        result = simulate_shooter(
            working_board,
            shooter,
            index,
        )
        results.append(result)

    total_removed = sum(
        result["removed_count"] for result in results
    )

    total_shots = sum(
        result["shots_used"] for result in results
    )

    remaining_pixels = sum(
        cell is not None
        for row in working_board
        for cell in row
    )

    return {
        "shooters_simulated": len(results),
        "total_shots_used": total_shots,
        "total_pixels_removed": total_removed,
        "remaining_pixels": remaining_pixels,
        "results": results,
        "final_board": working_board,
        "original_board_unchanged": original_board == original_copy,
        "gameplay_actions_performed": False,
    }


def run_tests():
    print("SEQUENTIAL FIRING SIMULATOR TESTS")
    print("=" * 48)

    tests = []

    def check(name, condition):
        tests.append((name, bool(condition)))

    # Test 1: A later shooter can remove a previous blocker.
    board = [
        ["cyan"],
        ["white"],
        ["cyan"],
    ]

    original = copy.deepcopy(board)

    shooters = [
        {
            "id": "cyan_first",
            "direction": "top_down",
            "lane": 0,
            "colour": "cyan",
            "ammo": 5,
        },
        {
            "id": "white_second",
            "direction": "top_down",
            "lane": 0,
            "colour": "white",
            "ammo": 5,
        },
        {
            "id": "cyan_third",
            "direction": "top_down",
            "lane": 0,
            "colour": "cyan",
            "ammo": 5,
        },
    ]

    result = simulate_sequence(board, shooters)

    check(
        "Sequential shooters expose and clear later targets",
        result["total_pixels_removed"] == 3
        and result["remaining_pixels"] == 0
        and result["results"][0]["status"]
        == "BLOCKED_BY_DIFFERENT_COLOUR"
        and result["results"][2]["removed_count"] == 1,
    )

    check(
        "Original board remains unchanged",
        board == original
        and result["original_board_unchanged"],
    )

    # Test 2: Removed cells can be passed through.
    board = [["cyan"], ["cyan"], ["white"]]

    result = simulate_sequence(board, [
        {
            "direction": "top_down",
            "lane": 0,
            "colour": "cyan",
            "ammo": 2,
        },
        {
            "direction": "bottom_up",
            "lane": 0,
            "colour": "white",
            "ammo": 2,
        },
    ])

    check(
        "Empty cells do not consume ammunition",
        result["total_pixels_removed"] == 3
        and result["remaining_pixels"] == 0,
    )

    # Test 3: Ammunition is respected.
    board = [["cyan"], ["cyan"], ["cyan"]]

    result = simulate_sequence(board, [
        {
            "direction": "top_down",
            "lane": 0,
            "colour": "cyan",
            "ammo": 1,
        },
    ])

    check(
        "Ammunition limit is respected",
        result["results"][0]["shots_used"] == 1
        and result["results"][0]["status"] == "AMMO_EXHAUSTED"
        and result["results"][0]["remaining_ammo"] == 0,
    )

    # Test 4: Different colour blocks firing.
    board = [["white"], ["cyan"]]

    result = simulate_sequence(board, [
        {
            "direction": "top_down",
            "lane": 0,
            "colour": "cyan",
            "ammo": 5,
        },
    ])

    check(
        "Different colour blocks the first shot",
        result["results"][0]["removed_count"] == 0
        and result["results"][0]["status"]
        == "BLOCKED_BY_DIFFERENT_COLOUR",
    )

    # Test 5: All four directions.
    direction_cases = [
        ("top_down", [["cyan"], ["cyan"]], 0, 2),
        ("bottom_up", [["cyan"], ["cyan"]], 0, 2),
        ("left_right", [["cyan", "cyan"]], 0, 2),
        ("right_left", [["cyan", "cyan"]], 0, 2),
    ]

    direction_passed = True

    for direction, board, lane, expected in direction_cases:
        result = simulate_sequence(board, [{
            "direction": direction,
            "lane": lane,
            "colour": "cyan",
            "ammo": 5,
        }])

        if result["total_pixels_removed"] != expected:
            direction_passed = False

    check("All four directions work", direction_passed)

    # Test 6: Empty shooter sequence.
    board = [["cyan"]]
    result = simulate_sequence(board, [])

    check(
        "Empty sequence leaves board unchanged",
        result["total_pixels_removed"] == 0
        and result["remaining_pixels"] == 1,
    )

    # Test 7: Invalid ammunition rejected.
    invalid_rejected = False

    try:
        simulate_sequence([["cyan"]], [{
            "direction": "top_down",
            "lane": 0,
            "colour": "cyan",
            "ammo": -1,
        }])
    except ValueError:
        invalid_rejected = True

    check("Invalid ammunition is rejected", invalid_rejected)

    # Test 8: Board boundaries are respected.
    board = [["cyan"], ["cyan"]]

    result = simulate_sequence(board, [{
        "direction": "top_down",
        "lane": 0,
        "colour": "cyan",
        "ammo": 10,
    }])

    check(
        "Firing stops at board boundary",
        result["results"][0]["status"] == "LANE_CLEARED"
        and result["results"][0]["removed_count"] == 2,
    )

    passed = 0

    for name, success in tests:
        print(f"[{'PASS' if success else 'FAIL'}] {name}")
        passed += int(success)

    print(f"\nTests passed: {passed}/{len(tests)}")

    if passed != len(tests):
        raise RuntimeError("Sequential simulator tests failed.")

    print("All sequential simulator tests passed.")


def main():
    run_tests()

    if not SOURCE.exists():
        print("\nLevel 39 source board not found; synthetic tests completed.")
        return

    data = strict_json_loads(SOURCE.read_text())
    board = data["board"]

    # Demonstration only. These are hypothetical shooters,
    # not verified Level 39 shooter assignments.
    demonstration = [
        {
            "id": "hypothetical_cyan",
            "direction": "top_down",
            "lane": 0,
            "colour": "cyan",
            "ammo": 40,
        },
        {
            "id": "hypothetical_white",
            "direction": "top_down",
            "lane": 0,
            "colour": "white",
            "ammo": 40,
        },
    ]

    result = simulate_sequence(board, demonstration)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, indent=2))

    print("\nLEVEL 39 — HYPOTHETICAL SEQUENCE")
    print("=" * 48)
    print("Shooters simulated:", result["shooters_simulated"])
    print("Total shots:", result["total_shots_used"])
    print("Pixels removed:", result["total_pixels_removed"])
    print("Remaining pixels:", result["remaining_pixels"])

    for item in result["results"]:
        print(
            item["shooter_id"],
            "| removed:", item["removed_count"],
            "| ammo left:", item["remaining_ammo"],
            "| status:", item["status"],
        )

    print("Report saved:", OUTPUT)
    print("Original board modified: NO")
    print("Gameplay actions performed: NO")


if __name__ == "__main__":
    main()
