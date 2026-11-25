import copy
import time

from game_state import GameState, DIRECTIONS
from solver import simulate_shot
from region_graph import build_region_graph


def inspect_lane(state, shooter_id, graph=None):
    shooter = state.shooters.get(shooter_id)
    if shooter is None:
        raise ValueError("Unknown shooter")
    if shooter.direction not in DIRECTIONS:
        raise ValueError("Invalid shooter direction")

    dx, dy = DIRECTIONS[shooter.direction]
    x, y = shooter.x + dx, shooter.y + dy

    while 0 <= x < state.width and 0 <= y < state.height:
        colour = state.pixel_at(x, y)
        if colour is not None:
            region_id = None if graph is None else graph["cell_region_ids"][y][x]
            return {
                "status": "EXPOSED_MATCHING_PIXEL" if colour == shooter.color
                          else "BLOCKED_BY_DIFFERENT_COLOUR",
                "position": [x, y],
                "colour": colour,
                "region_id": region_id,
            }
        x += dx
        y += dy

    return {
        "status": "NO_REACHABLE_PIXEL",
        "position": None,
        "colour": None,
        "region_id": None,
    }


def simulate_dynamic_board(state, shooter_id, max_shots=None, *, consume_state=False):
    if not isinstance(state, GameState):
        raise TypeError("Expected a GameState")
    errors = state.validate()
    if errors:
        raise ValueError("Invalid GameState: " + "; ".join(errors))
    if shooter_id not in state.shooters:
        raise ValueError("Unknown shooter")

    shooter = state.shooters[shooter_id]
    if shooter.ammo is None:
        raise ValueError("Shooter ammunition is unknown")
    if max_shots is not None and (type(max_shots) is not int or max_shots < 1):
        raise ValueError("max_shots must be a positive integer")

    if type(consume_state) is not bool:
        raise TypeError("consume_state must be a bool")
    initial_pixels = state.remaining_pixels
    initial_ammo = shooter.ammo
    # A caller may pass a disposable state copy. Avoid cloning it merely to
    # compute integrity metadata; the public default remains non-mutating.
    original = None if consume_state else copy.deepcopy(state)
    simulated = state if consume_state else copy.deepcopy(state)
    graph_started = time.perf_counter()
    graph = build_region_graph(simulated.board)
    graph_build_seconds = time.perf_counter() - graph_started
    graph_build_calls = 1
    shot_simulation_seconds = 0.0
    lane_inspection_seconds = 0.0
    steps, history = [], []

    limit = shooter.ammo if max_shots is None else min(shooter.ammo, max_shots)

    for index in range(limit):
        lane_started = time.perf_counter()
        before = inspect_lane(simulated, shooter_id, graph)
        lane_inspection_seconds += time.perf_counter() - lane_started
        shot_started = time.perf_counter()
        result = simulate_shot(simulated, shooter_id)
        shot_simulation_seconds += time.perf_counter() - shot_started
        step = {
            "shot_number": index + 1,
            "lane_before": before,
            "fired": result.fired,
            "removed": result.removed,
            "position": list(result.position) if result.position is not None else None,
            "reason": result.reason,
            "ammo_remaining": simulated.shooters[shooter_id].ammo,
        }

        if result.removed:
            graph_started = time.perf_counter()
            graph = build_region_graph(simulated.board)
            graph_build_seconds += time.perf_counter() - graph_started
            graph_build_calls += 1
            lane_started = time.perf_counter()
            step["lane_after"] = inspect_lane(simulated, shooter_id, graph)
            lane_inspection_seconds += time.perf_counter() - lane_started
            history.append({
                "after_shot": index + 1,
                "region_count": graph["region_count"],
                "occupied_cells": graph["occupied_cells"],
                "empty_cells": graph["empty_cells"],
            })

        steps.append(step)
        if not result.removed:
            break

    return {
        "engine": "build11ab_dynamic_board_simulator",
        "performance": {
            "region_graph_build_calls": graph_build_calls,
            "region_graph_build_seconds": round(graph_build_seconds, 6),
            "shot_simulation_seconds": round(shot_simulation_seconds, 6),
            "lane_inspection_seconds": round(lane_inspection_seconds, 6),
            "timing_clock": "time.perf_counter",
            "note": "Local simulation profiling only; not gameplay latency.",
        },
        "shooter_id": shooter_id,
        "initial_pixels": initial_pixels,
        "remaining_pixels": simulated.remaining_pixels,
        "pixels_removed": initial_pixels - simulated.remaining_pixels,
        "initial_ammo": initial_ammo,
        "remaining_ammo": simulated.shooters[shooter_id].ammo,
        "shots_attempted": len(steps),
        "steps": steps,
        "region_history": history,
        "final_region_graph": graph,
        # The simulated state is already isolated in the default mode; in
        # consume_state mode the caller explicitly supplied a disposable state.
        # Returning its board avoids a redundant full-grid deepcopy.
        "final_board": simulated.board,
        "source_state_unchanged": (
            state == original if original is not None else False
        ),
        "source_state_integrity_checked": original is not None,
        "dynamic_regions_rebuilt_after_removal": True,
        "gameplay_verified": False,
        "live_execution_allowed": False,
        "gameplay_actions_performed": False,
        "game_taps_enabled": False,
    }
