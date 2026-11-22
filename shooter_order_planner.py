#!/usr/bin/env python3
"""Read-only planner for ordering hypothetical Slime Loop shooter groups."""

import copy
import itertools
import json
from pathlib import Path

from sequential_firing_simulator import (
    SOURCE,
    simulate_sequence,
    validate_shooter,
)

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "data" / "shooter_order_plan_latest.json"
DEFAULT_CONVEYOR_CAPACITY = 5


def prepare_groups(shooters, conveyor_capacity=DEFAULT_CONVEYOR_CAPACITY):
    if not isinstance(shooters, list) or not shooters:
        raise ValueError("Supply a non-empty list of shooters.")

    if (
        not isinstance(conveyor_capacity, int)
        or isinstance(conveyor_capacity, bool)
        or conveyor_capacity < 1
    ):
        raise ValueError("Conveyor capacity must be a positive integer.")

    if len(shooters) > conveyor_capacity:
        raise ValueError(
            f"{len(shooters)} shooters exceed conveyor capacity "
            f"of {conveyor_capacity}."
        )

    groups = {}
    seen_ids = set()

    for index, shooter in enumerate(shooters, start=1):
        validate_shooter(shooter)

        shooter_id = shooter.get("id", f"shooter_{index}")

        if not isinstance(shooter_id, str) or not shooter_id.strip():
            raise ValueError("Shooter IDs must be non-empty strings.")

        if shooter_id in seen_ids:
            raise ValueError(f"Duplicate shooter ID: {shooter_id}")

        seen_ids.add(shooter_id)

        group_id = shooter.get("group_id")

        if group_id is None:
            group_key = f"__single__:{shooter_id}"
        else:
            if not isinstance(group_id, str) or not group_id.strip():
                raise ValueError("Group IDs must be non-empty strings.")
            group_key = f"group:{group_id}"

        groups.setdefault(group_key, []).append(copy.deepcopy(shooter))

    return groups


def score_result(result):
    blocked = sum(
        item["status"] == "BLOCKED_BY_DIFFERENT_COLOUR"
        for item in result["results"]
    )

    return (
        result["total_pixels_removed"],
        -result["remaining_pixels"],
        -blocked,
        -result["total_shots_used"],
    )


def plan_orders(
    board,
    shooters,
    conveyor_capacity=DEFAULT_CONVEYOR_CAPACITY,
):
    """Search group orders; members of a bonded group stay together."""

    groups = prepare_groups(shooters, conveyor_capacity)
    group_keys = list(groups)

    candidates = []

    for order in itertools.permutations(group_keys):
        ordered_shooters = []

        for group_key in order:
            ordered_shooters.extend(
                copy.deepcopy(groups[group_key])
            )

        result = simulate_sequence(board, ordered_shooters)

        candidate = {
            "group_order": list(order),
            "shooter_order": [
                shooter.get("id", "unnamed")
                for shooter in ordered_shooters
            ],
            "score": score_result(result),
            "result": result,
        }

        candidates.append(candidate)

    candidates.sort(
        key=lambda item: item["score"],
        reverse=True,
    )

    best = candidates[0]

    return {
        "groups_searched": len(groups),
        "orders_evaluated": len(candidates),
        "conveyor_capacity": conveyor_capacity,
        "shooters_planned": len(shooters),
        "best_group_order": best["group_order"],
        "best_shooter_order": best["shooter_order"],
        "best_score": list(best["score"]),
        "best_result": best["result"],
        "top_candidates": [
            {
                "group_order": item["group_order"],
                "shooter_order": item["shooter_order"],
                "pixels_removed": item["result"]["total_pixels_removed"],
                "remaining_pixels": item["result"]["remaining_pixels"],
                "blocked_shooters": sum(
                    r["status"] == "BLOCKED_BY_DIFFERENT_COLOUR"
                    for r in item["result"]["results"]
                ),
            }
            for item in candidates[:5]
        ],
        "gameplay_actions_performed": False,
    }


def run_tests():
    print("SHOOTER ORDER PLANNER TESTS")
    print("=" * 48)

    tests = []

    def check(name, condition):
        tests.append((name, bool(condition)))

    # Test 1: The best order clears all three cells.
    board = [["cyan"], ["white"], ["cyan"]]

    shooters = [
        {
            "id": "cyan_first",
            "direction": "top_down",
            "lane": 0,
            "colour": "cyan",
            "ammo": 5,
        },
        {
            "id": "white_middle",
            "direction": "top_down",
            "lane": 0,
            "colour": "white",
            "ammo": 5,
        },
        {
            "id": "cyan_last",
            "direction": "top_down",
            "lane": 0,
            "colour": "cyan",
            "ammo": 5,
        },
    ]

    plan = plan_orders(board, shooters)

    check(
        "Finds an order that clears all targets",
        plan["best_result"]["remaining_pixels"] == 0
        and plan["best_result"]["total_pixels_removed"] == 3,
    )

    check(
        "Evaluates every three-group ordering",
        plan["orders_evaluated"] == 6,
    )

    # Test 2: Bonded members remain adjacent and in supplied order.
    bonded_shooters = [
        {
            "id": "bond_a",
            "group_id": "bonded_pair",
            "direction": "top_down",
            "lane": 0,
            "colour": "cyan",
            "ammo": 2,
        },
        {
            "id": "bond_b",
            "group_id": "bonded_pair",
            "direction": "bottom_up",
            "lane": 1,
            "colour": "white",
            "ammo": 2,
        },
        {
            "id": "single_c",
            "direction": "left_right",
            "lane": 0,
            "colour": "cyan",
            "ammo": 2,
        },
    ]

    plan = plan_orders(
        [["cyan", "white"], ["cyan", "white"]],
        bonded_shooters,
    )

    best_order = plan["best_shooter_order"]
    bonded_positions = [
        best_order.index("bond_a"),
        best_order.index("bond_b"),
    ]

    check(
        "Bonded shooters remain together",
        bonded_positions[1] == bonded_positions[0] + 1,
    )

    check(
        "Bonded group member order is preserved",
        bonded_positions == sorted(bonded_positions),
    )

    # Test 3: Conveyor capacity is enforced.
    capacity_rejected = False

    try:
        plan_orders(
            [["cyan"]] * 6,
            [
                {
                    "id": f"s{i}",
                    "direction": "top_down",
                    "lane": 0,
                    "colour": "cyan",
                    "ammo": 1,
                }
                for i in range(6)
            ],
        )
    except ValueError:
        capacity_rejected = True

    check("Conveyor capacity is enforced", capacity_rejected)

    # Test 4: Duplicate IDs are rejected.
    duplicate_rejected = False

    try:
        plan_orders(
            [["cyan"]],
            [
                {
                    "id": "duplicate",
                    "direction": "top_down",
                    "lane": 0,
                    "colour": "cyan",
                    "ammo": 1,
                },
                {
                    "id": "duplicate",
                    "direction": "top_down",
                    "lane": 0,
                    "colour": "cyan",
                    "ammo": 1,
                },
            ],
        )
    except ValueError:
        duplicate_rejected = True

    check("Duplicate shooter IDs are rejected", duplicate_rejected)

    # Test 5: The source board remains unchanged.
    board = [["cyan"], ["white"], ["cyan"]]
    original = copy.deepcopy(board)

    plan_orders(board, shooters)

    check("Original board remains unchanged", board == original)

    # Test 6: One bonded group is treated as one ordering unit.
    plan = plan_orders(
        [["cyan", "white"]],
        bonded_shooters[:2],
    )

    check(
        "Single bonded group is evaluated as one unit",
        plan["groups_searched"] == 1
        and plan["orders_evaluated"] == 1,
    )

    passed = 0

    for name, success in tests:
        print(f"[{'PASS' if success else 'FAIL'}] {name}")
        passed += int(success)

    print(f"\nTests passed: {passed}/{len(tests)}")

    if passed != len(tests):
        raise RuntimeError("Shooter order planner tests failed.")

    print("All shooter order planner tests passed.")


def main():
    run_tests()

    if not SOURCE.exists():
        print("\nLevel 39 board not found; synthetic tests completed.")
        return

    data = json.loads(SOURCE.read_text())
    board = data["board"]

    # Hypothetical inputs only. These are NOT verified shooter positions.
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

    plan = plan_orders(board, demonstration)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(plan, indent=2))

    print("\nLEVEL 39 — HYPOTHETICAL ORDER SEARCH")
    print("=" * 48)
    print("Orders evaluated:", plan["orders_evaluated"])
    print("Best shooter order:", plan["best_shooter_order"])
    print("Pixels removed:", plan["best_result"]["total_pixels_removed"])
    print("Pixels remaining:", plan["best_result"]["remaining_pixels"])

    for candidate in plan["top_candidates"]:
        print(candidate)

    print("Report saved:", OUTPUT)
    print("Original board modified: NO")
    print("Gameplay actions performed: NO")


if __name__ == "__main__":
    main()
