"""Capacity-aware wrapper around evolving-board planning.

Each group is assigned its own conveyor batch. This conservative boundary
allows accessibility to be re-evaluated only between batches, after the
previous batch's abstract conveyor return cycle has been validated.
"""
import copy

from game_state import GameState
from conveyor_simulator import SimulatorConfig
from evolving_board_planner import plan_evolving_board
from dynamic_multi_batch import simulate_dynamic_multi_batch


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
    batches = [
        {
            "groups": [str(item["group_id"])],
            "reactivate_groups": [],
        }
        for item in sequence
    ]

    schedule = None
    if batches:
        schedule = simulate_dynamic_multi_batch(
            state,
            batches,
            config=config,
            allow_storage_reactivation=False,
            accessibility_resolver=accessibility_resolver,
        )

    known = set()
    for shooter_id, shooter in state.shooters.items():
        members = [str(shooter_id)] + [
            str(member) for member in shooter.bonded_ids
        ]
        known.add(str(shooter.group_id or min(members)))
    planned = {
        str(item["group_id"]) for item in sequence
    }
    unplanned = sorted(known - planned)
    board_cleared = bool(
        schedule and schedule.get("simulated_remaining_pixels") == 0
    )
    schedule_valid = bool(schedule and schedule.get("schedule_valid"))
    search_complete = not board_plan.get("search_truncated", False)
    full_level_complete = (
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
        board_plan.get("blockers", [])
    )
    if schedule and not schedule.get("schedule_valid"):
        blockers.append(
            schedule.get("scheduler_report", {}).get(
                "failure_reason", "SCHEDULER_REJECTED"
            )
        )

    return {
        "engine": "capacity_aware_evolving_schedule_v1",
        "status": (
            "SIMULATED_SCHEDULE_COMPLETE"
            if full_level_complete
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
        "full_level_complete": full_level_complete,
        "blockers": list(dict.fromkeys(blockers)),
        "source_state_unchanged": state == original,
        "source_state_integrity_checked": True,
        "accessibility_resolver_used": accessibility_resolver is not None,
        "evidence_verified": False,
        "live_execution_allowed": False,
        "gameplay_actions_performed": False,
        "game_taps_enabled": False,
        "limitations": [
            "Each group is isolated into its own batch to avoid assuming newly exposed groups were selectable earlier.",
            "Conveyor rotation timing is abstract and uncalibrated.",
            "Storage reactivation is disabled.",
            "Accessibility resolver output is a simulation assumption, not verified gameplay evidence.",
            "A complete simulation is not proof of a completed live game level.",
        ],
    }
