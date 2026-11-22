from sequential_firing_simulator import simulate_shooter


def run():
    tests = []

    def check(name, condition):
        tests.append((name, bool(condition)))

    # Final shot lands on the final board cell.
    result = simulate_shooter(
        [["cyan"]],
        {
            "direction": "top_down",
            "lane": 0,
            "colour": "cyan",
            "ammo": 1,
        },
        1,
    )
    check(
        "Final shot at board boundary reports exhaustion",
        result["status"] == "AMMO_EXHAUSTED"
        and result["shots_used"] == 1
        and result["next_cell"] is None,
    )

    # Final shot is followed by empty cells and then the boundary.
    result = simulate_shooter(
        [["cyan"], [None], [None]],
        {
            "direction": "top_down",
            "lane": 0,
            "colour": "cyan",
            "ammo": 1,
        },
        1,
    )
    check(
        "Empty cells after final shot do not change exhaustion",
        result["status"] == "AMMO_EXHAUSTED",
    )

    # Another occupied cell remains after ammunition is used.
    result = simulate_shooter(
        [["cyan"], ["white"]],
        {
            "direction": "top_down",
            "lane": 0,
            "colour": "cyan",
            "ammo": 1,
        },
        1,
    )
    check(
        "Exhaustion identifies the next occupied cell",
        result["status"] == "AMMO_EXHAUSTED"
        and result["next_cell"] == [1, 0]
        and result["next_cell_colour"] == "white",
    )

    # Ammunition remains when the path ends.
    result = simulate_shooter(
        [["cyan"]],
        {
            "direction": "top_down",
            "lane": 0,
            "colour": "cyan",
            "ammo": 2,
        },
        1,
    )
    check(
        "Unused ammunition reports lane cleared",
        result["status"] == "LANE_CLEARED"
        and result["remaining_ammo"] == 1,
    )

    # No target means no shot was needed.
    result = simulate_shooter(
        [[None]],
        {
            "direction": "top_down",
            "lane": 0,
            "colour": "cyan",
            "ammo": 0,
        },
        1,
    )
    check(
        "Empty lane with zero ammunition reports lane cleared",
        result["status"] == "LANE_CLEARED"
        and result["shots_used"] == 0,
    )

    print("AMMUNITION BOUNDARY TESTS")
    print("=" * 48)
    passed = 0

    for name, success in tests:
        print(f"[{'PASS' if success else 'FAIL'}] {name}")
        passed += int(success)

    print(f"\nTests passed: {passed}/{len(tests)}")

    if passed != len(tests):
        raise SystemExit("Ammunition boundary tests failed.")

    print("All ammunition boundary tests passed.")


if __name__ == "__main__":
    run()
