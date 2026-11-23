"""Capacity-aware wrapper around evolving-board planning.

Consecutive groups are packed together only when every member was accessible
at the batch start and conveyor capacity permits. Accessibility is refreshed
only at batch boundaries.
"""
import copy

from game_state import GameState
from conveyor_simulator import SimulatorConfig
from evolving_board_planner import plan_evolving_board
from dynamic_multi_batch import simulate_dynamic_multi_batch
from bonded_group_simulator import simulate_bonded_group
from accessibility_utils import normalize_accessible_ids


def plan_capacity_aware_evolving_schedule(
    state,
    accessibility_resolver=None,
    config=None,
    max_nodes=500,
    beam_width=40,
    max_depth=None,
):
    if not isinstance(state, GameState):
        raise TypeError("Expected a GameState")
    errors = state.validate()
    if errors:
        raise ValueError("Invalid GameState: " + "; ".join(errors))
    config = config or SimulatorConfig()
    original = copy.deepcopy(state)

    board_plan = plan_evolving_board(
        state,
        accessibility_resolver=accessibility_resolver,
        max_nodes=max_nodes,
        beam_width=beam_width,
        max_depth=max_depth,
    )
    sequence = board_plan.get("sequence", [])

    group_members = {}
    group_roots = {}
    for shooter_id in state.shooters:
        component = state.bonded_group(shooter_id)
        group_id = state.bonded_group_id(shooter_id)
        if not component or group_id is None:
            continue
        group_members[group_id] = set(component)
        group_roots[group_id] = min(component)

    # Pack consecutive groups only when all members were accessible at
    # batch start. Re-evaluate access only after evolving the private board
    # through the complete batch.
    probe = copy.deepcopy(state)
    batches = []
    cursor = 0
    while cursor < len(sequence):
        if accessibility_resolver is None:
            available = {
                str(shooter_id)
                for shooter_id, shooter in probe.shooters.items()
                if shooter.accessible
            }
        else:
            observed = accessibility_resolver(copy.deepcopy(probe))
            available = normalize_accessible_ids(observed)

        batch_groups = []
        batch_shooter_count = 0
        while cursor < len(sequence):
            group_id = str(sequence[cursor]["group_id"])
            members = group_members.get(group_id, set())
            if not members or not members.issubset(available):
                break
            if batch_shooter_count + len(members) > config.conveyor_capacity:
                break
            batch_groups.append(group_id)
            batch_shooter_count += len(members)
            cursor += 1

        if not batch_groups:
            break

        batches.append({"groups": list(batch_groups), "reactivate_groups": []})
        for group_id in batch_groups:
            isolated = copy.deepcopy(probe)
            isolated.conveyor = []
            isolated.storage = []
            for shooter_id, shooter in isolated.shooters.items():
                shooter.accessible = str(shooter_id) in available
            group_report = simulate_bonded_group(
                isolated, group_roots[group_id]
            )
            if group_report.get("status") != "SIMULATED":
                break
            probe.board = copy.deepcopy(group_report["final_board"])
            for shooter_id, ammo in group_report["remaining_ammo"].items():
                probe.shooters[shooter_id].ammo = ammo
                probe.shooters[shooter_id].accessible = False
        else:
            continue
        break
    schedule = None
    if batches:
        schedule = simulate_dynamic_multi_batch(
            state,
            batches,
            config=config,
            allow_storage_reactivation=False,
            accessibility_resolver=accessibility_resolver,
        )

    known = {
        group_id
        for shooter_id in state.shooters
        if (group_id := state.bonded_group_id(shooter_id)) is not None
    }
    planned = {
        str(item["group_id"]) for item in sequence
    }
    unplanned = sorted(known - planned)
    board_cleared = bool(
        schedule and schedule.get("simulated_remaining_pixels") == 0
    )
    schedule_valid = bool(schedule and schedule.get("schedule_valid"))
    search_complete = not board_plan.get("search_truncated", False)
    simulation_complete = (
        schedule_valid and board_cleared and not unplanned and search_complete
    )

    blockers = []
    if not schedule_valid:
        blockers.append("CAPACITY_SCHEDULE_NOT_VALID")
    if not board_cleared:
        blockers.append("BOARD_PIXELS_REMAIN_OR_BOARD_SIMULATION_UNAVAILABLE")
    if unplanned:
        blockers.append("KNOWN_GROUPS_NOT_PLANNED")
    if not search_complete:
        blockers.append("SEARCH_TRUNCATED")
    if accessibility_resolver is None:
        blockers.append("DYNAMIC_ACCESSIBILITY_UNVERIFIED")
    blockers.extend(
        item for item in board_plan.get("blockers", [])
        if not (
            item == "CONVEYOR_SCHEDULE_NOT_VALIDATED"
            and schedule_valid
        )
    )
    if schedule_valid:
        blockers.append("CONVEYOR_TIMING_UNCALIBRATED")
    if schedule and not schedule.get("schedule_valid"):
        blockers.append(
            schedule.get("scheduler_report", {}).get(
                "failure_reason", "SCHEDULER_REJECTED"
            )
        )

    return {
        "engine": "capacity_aware_evolving_schedule_v1",
        "status": (
            "SIMULATED_PLAN_COMPLETE"
            if simulation_complete
            else "SIMULATED_PARTIAL_OR_BLOCKED"
        ),
        "board_plan": {
            "status": board_plan.get("status"),
            "sequence": sequence,
            "nodes_examined": board_plan.get("nodes_examined", 0),
            "search_truncated": board_plan.get("search_truncated", False),
        },
        "batches": batches,
        "schedule_valid": schedule_valid,
        "scheduler_report": (
            schedule.get("scheduler_report") if schedule else None
        ),
        "group_simulations": (
            schedule.get("group_simulations", []) if schedule else []
        ),
        "initial_pixels": original.remaining_pixels,
        "simulated_remaining_pixels": (
            schedule.get("simulated_remaining_pixels")
            if schedule else original.remaining_pixels
        ),
        "simulated_pixels_removed": (
            schedule.get("simulated_pixels_removed", 0)
            if schedule else 0
        ),
        "board_cleared": board_cleared,
        "known_group_count": len(known),
        "planned_group_count": len(planned),
        "unplanned_group_ids": unplanned,
        "simulation_complete": simulation_complete,
        # A simulated schedule is never evidence that the live level is complete.
        "full_level_complete": False,
        "live_level_completion_verified": False,
        "blockers": list(dict.fromkeys(blockers)),
        "source_state_unchanged": state == original,
        "source_state_integrity_checked": True,
        "accessibility_resolver_used": accessibility_resolver is not None,
        "evidence_verified": False,
        "live_execution_allowed": False,
        "gameplay_actions_performed": False,
        "game_taps_enabled": False,
        "limitations": [
            "Consecutive groups share a batch only when all member shooters were accessible at that batch start and conveyor capacity permits.",
            "Conveyor rotation timing is abstract and uncalibrated.",
            "Storage reactivation is disabled.",
            "Accessibility resolver output is a simulation assumption, not verified gameplay evidence.",
            "A complete simulation is not proof of a completed live game level.",
        ],
    }
