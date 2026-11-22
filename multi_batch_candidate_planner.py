"""Build11AF: capacity-aware multi-batch candidate planning."""

import copy
import itertools
import math

from game_state import GameState
from execution_engine import available_groups
from dynamic_multi_batch import simulate_dynamic_multi_batch
from conveyor_simulator import SimulatorConfig


def _collect_groups(state):
    """Collect unique groups exposed by the existing accessibility rules."""
    result = []
    seen = set()

    for raw_group in available_groups(state):
        group = tuple(str(member) for member in raw_group)

        if not group or len(group) > 3:
            continue
        if any(member not in state.shooters for member in group):
            continue

        root_shooter = state.shooters[group[0]]
        group_id = str(
            getattr(root_shooter, "group_id", None)
            or min(group)
        )

        if group_id in seen:
            continue

        if any(
            member in state.conveyor or member in state.storage
            for member in group
        ):
            continue

        seen.add(group_id)
        result.append({
            "id": group_id,
            "members": group,
            "size": len(group),
        })

    return result


def _pack_batches(ordered_groups, initial_free, config):
    """Pack whole bonded groups without exceeding conveyor capacity."""
    capacity = config.conveyor_capacity

    if initial_free < 1:
        return None

    batches = []
    current = []
    available = min(initial_free, capacity)

    for group in ordered_groups:
        size = group["size"]

        if size > capacity:
            return None

        if size > available:
            if not current:
                return None

            batches.append({
                "groups": current,
                "reactivate_groups": [],
            })
            current = []
            available = capacity

        current.append(group["id"])
        available -= size

    if current:
        batches.append({
            "groups": current,
            "reactivate_groups": [],
        })

    return batches or None


def _candidate_score(report):
    valid = bool(report.get("schedule_valid"))
    removed = int(report.get("simulated_pixels_removed", 0))
    remaining = int(report.get("simulated_remaining_pixels", 10**9))

    shots = sum(
        int(value)
        for group in report.get("group_simulations", [])
        for value in group.get("shots", {}).values()
    )

    batch_count = len(report.get("prepared_batches", []))

    return (
        int(valid),
        removed,
        -remaining,
        -batch_count,
        -shots,
    )


def plan_multi_batch_candidates(
    state,
    max_candidates=2000,
    config=None,
):
    """Search group orders, form capacity-safe batches, and simulate them."""
    if not isinstance(state, GameState):
        raise TypeError("Expected a GameState")

    errors = state.validate()
    if errors:
        raise ValueError("Invalid GameState: " + "; ".join(errors))

    if (
        not isinstance(max_candidates, int)
        or isinstance(max_candidates, bool)
        or max_candidates < 1
    ):
        raise ValueError("max_candidates must be a positive integer")

    config = config or SimulatorConfig()
    original = copy.deepcopy(state)
    groups = _collect_groups(state)

    if not groups:
        return {
            "engine": "build11af_multi_batch_candidate_planner",
            "status": "NO_ACCESSIBLE_GROUPS",
            "candidate_count": 0,
            "best": None,
            "top_candidates": [],
            "source_state_unchanged": state == original,
            "evidence_verified": False,
            "live_execution_allowed": False,
            "gameplay_actions_performed": False,
            "game_taps_enabled": False,
        }

    total_orders = math.factorial(len(groups))
    candidates = []
    examined = 0
    failures = []

    for order in itertools.islice(
        itertools.permutations(groups),
        max_candidates,
    ):
        batches = _pack_batches(
            order,
            state.conveyor_free,
            config,
        )

        if batches is None:
            continue

        planning_state = copy.deepcopy(state)

        # Build11AE's group index can resolve a group to its last member.
        # Make every member of an already-accessible group selectable
        # only inside this private simulation copy.
        for group in order:
            for member in group["members"]:
                planning_state.shooters[member].accessible = True

        try:
            report = simulate_dynamic_multi_batch(
                planning_state,
                batches,
                config=config,
                allow_storage_reactivation=False,
            )
        except Exception as exc:
            failures.append({
                "groups": [item["id"] for item in order],
                "error": str(exc),
            })
            examined += 1
            continue

        report["candidate_order"] = [
            item["id"] for item in order
        ]
        report["candidate_batches"] = copy.deepcopy(batches)
        report["score"] = list(_candidate_score(report))
        candidates.append(report)
        examined += 1

    candidates.sort(
        key=lambda item: tuple(item["score"]),
        reverse=True,
    )

    best = candidates[0] if candidates else None
    unchanged = state == original
    truncated = total_orders > max_candidates

    return {
        "engine": "build11af_multi_batch_candidate_planner",
        "status": (
            "SIMULATED"
            if best and best.get("schedule_valid")
            else "NO_VALID_MULTI_BATCH_PLAN"
        ),
        "accessible_group_count": len(groups),
        "candidate_count": examined,
        "valid_candidate_count": sum(
            bool(item.get("schedule_valid"))
            for item in candidates
        ),
        "candidate_limit": max_candidates,
        "search_truncated": truncated,
        "best": best,
        "top_candidates": candidates[:5],
        "candidate_errors": failures[:10],
        "source_state_unchanged": unchanged,
        "source_state_integrity_checked": True,
        "evidence_verified": False,
        "live_execution_allowed": False,
        "gameplay_actions_performed": False,
        "game_taps_enabled": False,
        "limitations": [
            "Only groups currently exposed by the accessibility model are considered.",
            "Conveyor timing remains abstract and uncalibrated.",
            "Storage reactivation is disabled.",
            "Board simulation is not validated against live gameplay.",
            "A valid simulation does not authorize game taps.",
        ],
    }
