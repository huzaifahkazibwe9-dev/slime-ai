#!/usr/bin/env python3
"""Read-only adapter between firing_simulator and firing_evaluator."""

from game_state import GameState
from firing_evaluator import evaluate_firing_target


DIRECTION_MAP = {
    "top_down": ("down", lambda state, lane: (lane, 0)),
    "bottom_up": ("up", lambda state, lane: (lane, state.height - 1)),
    "left_right": ("right", lambda state, lane: (0, lane)),
    "right_left": ("left", lambda state, lane: (state.width - 1, lane)),
}


def evaluate_lane_target(state, simulator_direction, lane, shooter_colour=None):
    """Evaluate the first occupied cell in a simulator-style lane."""
    if simulator_direction not in DIRECTION_MAP:
        raise ValueError(f"Unsupported simulator direction: {simulator_direction}")

    if not isinstance(lane, int) or isinstance(lane, bool):
        raise ValueError("Lane must be an integer.")

    game_direction, entry_function = DIRECTION_MAP[simulator_direction]

    limit = state.width if simulator_direction in ("top_down", "bottom_up") else state.height

    if not 0 <= lane < limit:
        raise ValueError(f"Lane must be between 0 and {limit - 1}.")

    entry_cell = entry_function(state, lane)

    result = evaluate_firing_target(
        state,
        entry_cell,
        game_direction,
        shooter_colour,
    )

    result["simulator_direction"] = simulator_direction
    result["lane"] = lane
    result["entry_cell"] = entry_cell
    return result


def run_tests():
    print("FIRING ADAPTER TESTS")
    print("=" * 45)

    tests = []

    def check(name, condition):
        tests.append((name, bool(condition)))

    # Each test uses a separate state.
    board = [[None] * 35 for _ in range(35)]
    board[0][4] = "cyan"
    state = GameState(board)
    result = evaluate_lane_target(state, "top_down", 4, "cyan")
    check("Top fires downward with correct coordinates",
          result["status"] == "MATCH" and result["cell"] == (4, 0))

    board = [[None] * 35 for _ in range(35)]
    board[34][4] = "cyan"
    state = GameState(board)
    result = evaluate_lane_target(state, "bottom_up", 4, "cyan")
    check("Bottom fires upward with correct coordinates",
          result["status"] == "MATCH" and result["cell"] == (4, 34))

    board = [[None] * 35 for _ in range(35)]
    board[7][0] = "cyan"
    state = GameState(board)
    result = evaluate_lane_target(state, "left_right", 7, "cyan")
    check("Left fires rightward with correct coordinates",
          result["status"] == "MATCH" and result["cell"] == (0, 7))

    board = [[None] * 35 for _ in range(35)]
    board[7][34] = "cyan"
    state = GameState(board)
    result = evaluate_lane_target(state, "right_left", 7, "cyan")
    check("Right fires leftward with correct coordinates",
          result["status"] == "MATCH" and result["cell"] == (34, 7))

    board = [[None] * 35 for _ in range(35)]
    board[0][4] = "white"
    board[1][4] = "cyan"
    state = GameState(board)
    result = evaluate_lane_target(state, "top_down", 4, "cyan")
    check("Different first colour blocks matching cell behind it",
          result["status"] == "BLOCKED_BY_DIFFERENT_COLOUR"
          and result["cell"] == (4, 0))

    board = [[None] * 35 for _ in range(35)]
    state = GameState(board)
    result = evaluate_lane_target(state, "top_down", 4, "cyan")
    check("Empty lane reports no target",
          result["status"] == "NO_TARGET" and result["cell"] is None)

    passed = 0
    for name, success in tests:
        print(f"[{'PASS' if success else 'FAIL'}] {name}")
        passed += int(success)

    print(f"\nTests passed: {passed}/{len(tests)}")
    if passed != len(tests):
        raise RuntimeError("Firing adapter tests failed.")

    print("All firing adapter tests passed.")


if __name__ == "__main__":
    run_tests()
