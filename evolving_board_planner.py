"""Bounded board-state search with an explicit accessibility resolver.

This planner explores how clearing pixels can change later board shots.
It does not model conveyor timing or authorize game actions.
"""
import copy

from game_state import GameState
from planner import available_groups
from bonded_group_simulator import simulate_bonded_group


def _group_key(state, members):
    shooter = state.shooters[str(members[0])]
    ids = [str(members[0])] + [
        str(value) for value in shooter.bonded_ids
    ]
    return str(shooter.group_id or min(ids))


def _state_key(state, used):
    board = tuple(tuple(row) for row in state.board)
    ammo = tuple(sorted(
        (str(key), value.ammo)
        for key, value in state.shooters.items()
    ))
    return board, ammo, tuple(sorted(used))


def _normalise_accessibility(state, resolver):
    """Refresh accessible flags only from the supplied resolver."""
    if resolver is None:
        return
    observed = resolver(copy.deepcopy(state))
    if observed is None:
        observed = []
    allowed = {str(value) for value in observed}
    for shooter_id, shooter in state.shooters.items():
        shooter.accessible = str(shooter_id) in allowed


def _known_group_ids(state):
    groups = set()
    for shooter_id, shooter in state.shooters.items():
        members = [str(shooter_id)] + [
            str(value) for value in shooter.bonded_ids
        ]
        groups.add(str(shooter.group_id or min(members)))
    return groups


def plan_evolving_board(
    state,
    accessibility_resolver=None,
    max_nodes=500,
    beam_width=40,
    max_depth=None,
):
    """Search sequential group choices while recalculating board state.

    accessibility_resolver, when supplied, receives an isolated GameState
    copy and returns shooter IDs observed to be accessible in that state.
    Without it, only accessibility already present in the input is used.
    """
    if not isinstance(state, GameState):
        raise TypeError("Expected a GameState")
    errors = state.validate()
    if errors:
        raise ValueError("Invalid GameState: " + "; ".join(errors))
    for name, value in (("max_nodes", max_nodes), ("beam_width", beam_width)):
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise ValueError(name + " must be a positive integer")
    if max_depth is not None and (
        not isinstance(max_depth, int) or isinstance(max_depth, bool)
        or max_depth < 1
    ):
        raise ValueError("max_depth must be a positive integer or None")
    if accessibility_resolver is not None and not callable(accessibility_resolver):
        raise TypeError("accessibility_resolver must be callable")

    original = copy.deepcopy(state)
    root = copy.deepcopy(state)
    _normalise_accessibility(root, accessibility_resolver)
    frontier = [{
        "state": root,
        "used": frozenset(),
        "order": [],
        "removed": 0,
    }]
    visited = {_state_key(root, ())}
    examined = 0
    truncated = False
    solutions = []
    best = frontier[0]
    depth_limit = max_depth or max(1, len(state.shooters))

    while frontier and examined < max_nodes:
        expanded = []
        for node in frontier:
            current = node["state"]
            if current.remaining_pixels < best["state"].remaining_pixels:
                best = node
            if current.remaining_pixels == 0:
                solutions.append(node)
                continue
            if len(node["order"]) >= depth_limit:
                continue

            groups = list(available_groups(current))
            for group in groups:
                if examined >= max_nodes:
                    truncated = True
                    break
                group = tuple(str(member) for member in group)
                group_id = _group_key(current, group)
                if group_id in node["used"]:
                    continue

                isolated = copy.deepcopy(current)
                isolated.conveyor = []
                isolated.storage = []
                for member in group:
                    isolated.shooters[member].accessible = True

                try:
                    report = simulate_bonded_group(isolated, group[0])
                except Exception:
                    examined += 1
                    continue
                examined += 1
                if report.get("status") != "SIMULATED":
                    continue

                child = copy.deepcopy(current)
                child.board = copy.deepcopy(report["final_board"])
                for shooter_id, ammo in report["remaining_ammo"].items():
                    child.shooters[shooter_id].ammo = ammo
                child.conveyor = []
                child.storage = []
                for shooter in child.shooters.values():
                    shooter.accessible = False
                _normalise_accessibility(child, accessibility_resolver)

                used = frozenset(set(node["used"]) | {group_id})
                key = _state_key(child, used)
                if key in visited:
                    continue
                visited.add(key)
                child_node = {
                    "state": child,
                    "used": used,
                    "order": node["order"] + [{
                        "group_id": group_id,
                        "shooter_ids": list(group),
                        "pixels_removed": report["pixels_removed"],
                        "shots_attempted": report["shots_attempted"],
                    }],
                    "removed": original.remaining_pixels - child.remaining_pixels,
                }
                expanded.append(child_node)
                if child.remaining_pixels < best["state"].remaining_pixels:
                    best = child_node
                if child.remaining_pixels == 0:
                    solutions.append(child_node)
            if truncated:
                break

        expanded.sort(key=lambda item: (
            item["state"].remaining_pixels,
            len(item["order"]),
            sum(
                shooter.ammo or 0
                for shooter in item["state"].shooters.values()
            ),
        ))
        frontier = expanded[:beam_width]
        if len(expanded) > beam_width:
            truncated = True

    solutions.sort(key=lambda item: (
        len(item["order"]),
        sum(shooter.ammo or 0 for shooter in item["state"].shooters.values()),
    ))
    chosen = solutions[0] if solutions else best
    remaining = chosen["state"].remaining_pixels
    known = _known_group_ids(state)
    planned = set(chosen["used"])
    blockers = []
    if remaining:
        blockers.append("BOARD_PIXELS_REMAIN")
    if truncated:
        blockers.append("SEARCH_TRUNCATED")
    if accessibility_resolver is None:
        blockers.append("DYNAMIC_ACCESSIBILITY_UNVERIFIED")
    if not solutions:
        blockers.append("NO_COMPLETE_BOARD_SEQUENCE_FOUND")

    return {
        "engine": "evolving_board_beam_search_v1",
        "status": "BOARD_SEQUENCE_FOUND" if solutions else "PARTIAL_SEQUENCE",
        "nodes_examined": examined,
        "node_limit": max_nodes,
        "beam_width": beam_width,
        "search_truncated": truncated,
        "depth_limit": depth_limit,
        "sequence": chosen["order"],
        "sequence_length": len(chosen["order"]),
        "initial_pixels": original.remaining_pixels,
        "simulated_remaining_pixels": remaining,
        "simulated_pixels_removed": original.remaining_pixels - remaining,
        "board_cleared": remaining == 0,
        "known_group_count": len(known),
        "planned_group_ids": sorted(planned),
        "unplanned_group_ids": sorted(known - planned),
        "full_level_complete": False,
        "blockers": blockers + ["CONVEYOR_SCHEDULE_NOT_VALIDATED"],
        "source_state_unchanged": state == original,
        "source_state_integrity_checked": True,
        "evidence_verified": False,
        "live_execution_allowed": False,
        "gameplay_actions_performed": False,
        "game_taps_enabled": False,
        "limitations": [
            "Accessibility changes are considered only when supplied by an explicit resolver.",
            "Resolver output is a planning assumption, not verified gameplay evidence.",
            "Conveyor timing, storage occupancy and reactivation are not simulated.",
            "A cleared board sequence is not a validated complete-level execution plan.",
        ],
    }
