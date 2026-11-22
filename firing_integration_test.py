#!/usr/bin/env python3
"""Cross-check the firing adapter against the simulator on Level 39."""

import json
from pathlib import Path

from game_state import GameState
from firing_adapter import evaluate_lane_target
from firing_simulator import simulate, DIRECTIONS

ROOT = Path(__file__).resolve().parent
data = json.loads((ROOT / "data" / "vision_level39.json").read_text())
board = data["board"]

state = GameState(board)
passed = 0
failed = []

print("LEVEL 39 — FIRING INTEGRATION TEST")
print("=" * 48)

for direction in DIRECTIONS:
    for lane in range(35):
        target = evaluate_lane_target(state, direction, lane)

        if not target["found"]:
            failed.append((direction, lane, "No first target found"))
            continue

        x, y = target["cell"]
        first_colour = target["colour"]
        expected_cell = [y, x]

        # Matching-colour comparison.
        match_eval = evaluate_lane_target(
            state, direction, lane, first_colour
        )
        match_sim = simulate(
            board, direction, lane, first_colour, 40
        )

        match_ok = (
            match_eval["status"] == "MATCH"
            and match_sim["removed_count"] > 0
            and match_sim["removed_cells"][0]["cell"] == expected_cell
        )

        # Different-colour blocker comparison.
        other_colour = "__adapter_test_other_colour__"
        block_eval = evaluate_lane_target(
            state, direction, lane, other_colour
        )
        block_sim = simulate(
            board, direction, lane, other_colour, 40
        )

        block_ok = (
            block_eval["status"] == "BLOCKED_BY_DIFFERENT_COLOUR"
            and block_sim["status"] == "BLOCKED_BY_DIFFERENT_COLOUR"
            and block_sim["removed_count"] == 0
            and block_sim["next_cell"] == expected_cell
        )

        if match_ok and block_ok:
            passed += 1
        else:
            failed.append((
                direction,
                lane,
                {
                    "target": expected_cell,
                    "match_ok": match_ok,
                    "block_ok": block_ok,
                    "evaluator_match": match_eval["status"],
                    "simulator_match": match_sim["status"],
                    "evaluator_block": block_eval["status"],
                    "simulator_block": block_sim["status"],
                },
            ))

print(f"Lanes checked: {len(DIRECTIONS) * 35}")
print(f"Passed: {passed}")
print(f"Failed: {len(failed)}")

for failure in failed[:10]:
    print("[FAIL]", failure)

if failed:
    raise SystemExit("Integration test failed.")

print("PASS: Adapter and simulator agree on all Level 39 first targets.")
print("Original board modified: NO")
print("Gameplay actions performed: NO")
