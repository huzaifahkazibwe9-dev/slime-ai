import copy

from game_state import GameState
from dynamic_board_simulator import simulate_dynamic_board
from region_graph import build_region_graph


def simulate_bonded_group(state, shooter_id):
    """Dry-run one complete legal bonded group on an isolated state copy."""
    if not isinstance(state, GameState):
        raise TypeError("Expected a GameState")

    errors = state.validate()
    if errors:
        raise ValueError("Invalid GameState: " + "; ".join(errors))

    if shooter_id not in state.shooters:
        raise ValueError("Unknown shooter")

    group = state.bonded_group(shooter_id)
    if not group:
        raise ValueError("Invalid or incomplete bonded group")

    if not state.can_select_group(shooter_id):
        return {
            "status": "GROUP_NOT_SELECTABLE",
            "shooter_ids": list(group),
            "reason": "Group is inaccessible or lacks conveyor capacity",
            "gameplay_verified": False,
            "live_execution_allowed": False,
            "game_taps_enabled": False,
        }

    original = copy.deepcopy(state)
    working = copy.deepcopy(state)

    if not working.select_group(shooter_id):
        raise RuntimeError("Group selection failed on simulation copy")

    member_reports = []
    total_removed = 0
    total_shots = 0
    region_history = []

    for member_id in group:
        report = simulate_dynamic_board(working, member_id)

        working.board = copy.deepcopy(report["final_board"])
        working.shooters[member_id].ammo = report["remaining_ammo"]

        total_removed += report["pixels_removed"]
        total_shots += report["shots_attempted"]

        member_reports.append({
            "shooter_id": member_id,
            "initial_ammo": report["initial_ammo"],
            "remaining_ammo": report["remaining_ammo"],
            "shots_attempted": report["shots_attempted"],
            "pixels_removed": report["pixels_removed"],
            "steps": report["steps"],
        })

        region_history.append({
            "shooter_id": member_id,
            "history": report["region_history"],
        })

    final_graph = build_region_graph(working.board)
    unchanged = state == original

    return {
        "engine": "build11ac_bonded_group_dynamic_simulator",
        "status": "SIMULATED",
        "shooter_ids": list(group),
        "group_selected_atomically": all(
            member in working.conveyor for member in group
        ),
        "conveyor_after_selection": list(working.conveyor),
        "initial_pixels": original.remaining_pixels,
        "remaining_pixels": working.remaining_pixels,
        "pixels_removed": total_removed,
        "shots_attempted": total_shots,
        "member_reports": member_reports,
        "region_history": region_history,
        "final_region_graph": final_graph,
        "final_board": copy.deepcopy(working.board),
        "remaining_ammo": {
            member: working.shooters[member].ammo for member in group
        },
        "source_state_unchanged": unchanged,
        "source_state_integrity_checked": True,
        "dynamic_regions_rebuilt": True,
        "gameplay_verified": False,
        "evidence_verified": False,
        "live_execution_allowed": False,
        "gameplay_actions_performed": False,
        "game_taps_enabled": False,
    }
