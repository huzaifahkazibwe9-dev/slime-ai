"""Single-batch, simulation-only Slime Loop execution engine."""
import copy

from game_state import GameState
from planner import available_groups
from solver import simulate_shot
from bonded_group_simulator import simulate_bonded_group
from conveyor_simulator import create_simulator, SimulatorConfig

MAX_CANDIDATES = 2000


def _fire_shooter(state, shooter_id):
    shooter = state.shooters[shooter_id]
    log = []

    while shooter.ammo is not None and shooter.ammo > 0:
        result = simulate_shot(state, shooter_id)
        log.append({
            "removed": bool(result.removed),
            "position": list(result.position) if result.position is not None else None,
            "reason": result.reason,
        })
        if not result.removed:
            break

    return {
        "shooter_id": shooter_id,
        "shots_attempted": len(log),
        "pixels_removed": sum(item["removed"] for item in log),
        "remaining_ammo": shooter.ammo,
        "shot_log": log,
    }



def _simulate_conveyor_batch(original, state, groups):
    """Simulate candidate groups alongside existing conveyor occupants.

    rotation_progress is mapped to the nearest abstract tick. This remains
    approximate until actual game rotation timing is calibrated.
    """
    storage = getattr(original, "storage", [])
    if isinstance(storage, dict):
        occupied = sum(value is not None for value in storage.values())
    elif isinstance(storage, (list, tuple)):
        occupied = sum(value is not None for value in storage)
    else:
        occupied = len(storage)

    config = SimulatorConfig()
    records = []

    # Existing conveyor occupants must represent complete bonded groups.
    # A partial group cannot be safely reconstructed from the screenshot/state.
    conveyor_ids = {str(item) for item in original.conveyor}
    checked_groups = set()
    for shooter_id in original.conveyor:
        members = original.bonded_group(shooter_id)
        if not members:
            return {
                "failed": True,
                "batch_selection_valid": False,
                "failure_reason": "INVALID_EXISTING_CONVEYOR_GROUP",
            }
        canonical_id = original.bonded_group_id(shooter_id)
        if canonical_id is None:
            return {
                "failed": True,
                "batch_selection_valid": False,
                "failure_reason": "INVALID_BONDED_GROUP_IDENTITY",
            }
        if canonical_id in checked_groups:
            continue
        checked_groups.add(canonical_id)
        if not set(members).issubset(conveyor_ids):
            return {
                "failed": True,
                "batch_selection_valid": False,
                "failure_reason": "PARTIAL_BONDED_GROUP_ON_CONVEYOR",
                "group_id": canonical_id,
                "required_shooter_ids": members,
                "conveyor_shooter_ids": sorted(conveyor_ids),
            }

    # Restore shooters already on the conveyor. Bonded members must map
    # to the same abstract tick; GameState validates each progress value
    # independently, so verify group synchronization before simulator creation.
    existing_group_positions = {}
    for shooter_id in original.conveyor:
        shooter = original.shooters[shooter_id]
        if shooter.ammo is None:
            return {
                "failed": True,
                "batch_selection_valid": False,
                "failure_reason": "UNKNOWN_AMMO_ON_EXISTING_CONVEYOR",
                "shooter_id": str(shooter_id),
            }
        group_id = original.bonded_group_id(shooter_id)
        if group_id is None:
            return {
                "failed": True,
                "batch_selection_valid": False,
                "failure_reason": "INVALID_BONDED_GROUP_IDENTITY",
            }
        progress = float(shooter.rotation_progress or 0.0)
        position = int(round(progress * config.ticks_per_lap))
        position %= config.ticks_per_lap
        existing_group_positions.setdefault(group_id, set()).add(position)

        records.append({
            "id": str(shooter_id),
            "group_id": str(group_id),
            "ammo": shooter.ammo,
            "position": position,
            "selected": True,
        })

    for group_id, positions in existing_group_positions.items():
        if len(positions) > 1:
            return {
                "failed": True,
                "batch_selection_valid": False,
                "failure_reason": "UNSYNCHRONIZED_BONDED_GROUP_ON_CONVEYOR",
                "group_id": group_id,
                "abstract_positions": sorted(positions),
            }

    # Add candidate shooters as not-yet-selected.
    for group in groups:
        root = str(group[0])
        canonical_group_id = original.bonded_group_id(root)
        if canonical_group_id is None:
            return {
                "failed": True,
                "batch_selection_valid": False,
                "failure_reason": "INVALID_BONDED_GROUP_IDENTITY",
            }
        for shooter_id in group:
            if original.bonded_group_id(shooter_id) != canonical_group_id:
                return {
                    "failed": True,
                    "batch_selection_valid": False,
                    "failure_reason": "INCONSISTENT_BONDED_GROUP_MEMBERSHIP",
                }
            source_shooter = original.shooters[shooter_id]
            simulated_shooter = state.shooters[shooter_id]
            if type(source_shooter.ammo) is not int or source_shooter.ammo < 0:
                return {
                    "failed": True,
                    "batch_selection_valid": False,
                    "failure_reason": "UNKNOWN_OR_INVALID_AMMO_ON_CANDIDATE_SHOOTER",
                    "shooter_id": str(shooter_id),
                }
            if (
                type(simulated_shooter.ammo) is not int
                or simulated_shooter.ammo < 0
                or simulated_shooter.ammo > source_shooter.ammo
            ):
                return {
                    "failed": True,
                    "batch_selection_valid": False,
                    "failure_reason": "INVALID_SIMULATED_AMMO_STATE",
                    "shooter_id": str(shooter_id),
                }
            records.append({
                "id": str(shooter_id),
                "group_id": str(canonical_group_id),
                "ammo": source_shooter.ammo,
            })

    sim = create_simulator(
        records,
        storage_occupied=occupied,
        config=config,
    )

    selected = True
    for group in groups:
        canonical_group_id = original.bonded_group_id(str(group[0]))
        if canonical_group_id is None or not sim.select_group(str(canonical_group_id)):
            selected = False
            break

    if selected:
        for group in groups:
            for shooter_id in group:
                initial = original.shooters[shooter_id].ammo
                remaining = state.shooters[shooter_id].ammo
                consumed = initial - remaining

                if not sim.record_shots(str(shooter_id), consumed):
                    selected = False
                    break

            if not selected:
                break

    if selected:
        sim.tick(sim.config.ticks_per_lap)

    report = sim.report()
    report["batch_selection_valid"] = selected
    report["storage_occupancy_source"] = "original_game_state"
    report["existing_conveyor_shooters"] = list(original.conveyor)
    report["existing_conveyor_state_restored"] = True
    report["rotation_progress_mapping"] = "nearest_abstract_tick"
    report["rotation_progress_mapping_calibrated"] = False
    return report

def _simulate_order(original, groups):
    state = copy.deepcopy(original)
    actions = []
    firing = []

    group_simulations = []

    for group in groups:
        root = group[0]

        # This candidate already owns a private state copy, so consume it
        # directly instead of cloning and replaying the same group simulation.
        group_report = simulate_bonded_group(
            state, root, consume_state=True
        )
        if (
            group_report.get("status") != "SIMULATED"
            or group_report.get("shooter_ids") != list(group)
            or not group_report.get("group_selected_atomically")
            or not all(member in state.conveyor for member in group)
            or group_report.get("final_board") != state.board
        ):
            return None

        for shooter_id in group:
            if (
                shooter_id not in group_report["remaining_ammo"]
                or state.shooters[shooter_id].ammo
                != group_report["remaining_ammo"][shooter_id]
            ):
                return None

        group_simulations.append(group_report)

        actions.append({
            "type": "SIMULATED_GROUP_SELECTION",
            "shooter_ids": list(group),
            "group_selected_atomically": group_report.get(
                "group_selected_atomically", False
            ),
        })

        member_reports = {
            item["shooter_id"]: item
            for item in group_report["member_reports"]
        }

        for shooter_id in group:
            member = member_reports[shooter_id]
            shot_log = [
                {
                    "removed": bool(step.get("removed")),
                    "position": step.get("position"),
                    "reason": step.get("reason"),
                }
                for step in member["steps"]
            ]

            result = {
                "shooter_id": shooter_id,
                "shots_attempted": member["shots_attempted"],
                "pixels_removed": member["pixels_removed"],
                "remaining_ammo": member["remaining_ammo"],
                "shot_log": shot_log,
                "dynamic_regions_rebuilt": True,
            }

            firing.append(result)
            actions.append({
                "type": "SIMULATED_FIRING",
                "shooter_id": shooter_id,
                "pixels_removed": result["pixels_removed"],
            })

    conveyor_report = _simulate_conveyor_batch(
        original, state, groups
    )
    conveyor_safe = (
        conveyor_report["batch_selection_valid"]
        and not conveyor_report["failed"]
    )

    removed = original.remaining_pixels - state.remaining_pixels
    blocked = sum(
        1
        for item in firing
        for shot in item["shot_log"]
        if shot["reason"] == "Blocked by another colour"
    )
    shots = sum(item["shots_attempted"] for item in firing)

    return {
        "groups": [list(group) for group in groups],
        "actions": actions,
        "firing": firing,
        "bonded_group_simulations": group_simulations,
        "dynamic_regions_rebuilt": all(
            report.get("dynamic_regions_rebuilt")
            for report in group_simulations
        ),
        "conveyor_safe": conveyor_safe,
        "conveyor_simulation": conveyor_report,
        "pixels_removed": removed,
        "remaining_pixels": state.remaining_pixels,
        "shots_attempted": shots,
        "blocked_attempts": blocked,
        "conveyor_used": len(state.conveyor) - len(original.conveyor),
        "final_board": copy.deepcopy(state.board),
        "score": (removed, -state.remaining_pixels, -blocked, -shots),
    }


def run_dry_simulation(state, max_candidates=MAX_CANDIDATES):
    """Search legal accessible group orders within one conveyor batch."""
    if not isinstance(state, GameState):
        raise TypeError("Expected a GameState")

    if state.validate():
        raise ValueError("GameState validation failed")

    # Screenshot-derived states carry an explicit provenance gate. If the
    # shooter panel cannot be tied to the board screenshot/session, do not
    # produce a candidate plan from a potentially mixed capture.
    if (hasattr(state, "shooter_capture_provenance_verified")
            and state.shooter_capture_provenance_verified is not True):
        return {
            "engine": "single_batch_dry_run_v1",
            "status": "BLOCKED_UNVERIFIED_CAPTURE_PROVENANCE",
            "initial_pixels": state.remaining_pixels,
            "accessible_group_count": 0,
            "candidates_examined": 0,
            "candidate_limit": max_candidates,
            "search_truncated": False,
            "best": None,
            "top_candidates": [],
            "source_state_unchanged": True,
            "evidence_verified": False,
            "live_execution_allowed": False,
            "gameplay_actions_performed": False,
            "limitations": [
                "Board and shooter observations must share verified screenshot provenance.",
                "No candidate plan is produced from mismatched or unverified captures.",
            ],
        }

    if (not isinstance(max_candidates, int)
            or isinstance(max_candidates, bool)
            or max_candidates < 1):
        raise ValueError("max_candidates must be a positive integer")

    original = copy.deepcopy(state)
    groups = [
        tuple(group)
        for group in available_groups(state)
        if group and len(group) <= state.conveyor_free
    ]

    candidates = []
    examined = 0
    truncated = False

    def visit(prefix, used, remaining):
        nonlocal examined, truncated

        if prefix:
            if examined >= max_candidates:
                truncated = True
                return

            result = _simulate_order(original, prefix)
            examined += 1

            if result is not None:
                candidates.append(result)

        if examined >= max_candidates:
            truncated = True
            return

        for index, group in enumerate(remaining):
            size = len(group)

            if used + size <= original.conveyor_free:
                visit(
                    prefix + (group,),
                    used + size,
                    remaining[:index] + remaining[index + 1:],
                )

                if examined >= max_candidates:
                    truncated = True
                    return

    visit((), 0, groups)
    candidates.sort(
        key=lambda item: (item["conveyor_safe"], item["score"]),
        reverse=True
    )
    best = candidates[0] if candidates else None

    unchanged = (
        state.board == original.board
        and state.conveyor == original.conveyor
        and state.storage == original.storage
        and {
            key: value.ammo for key, value in state.shooters.items()
        } == {
            key: value.ammo for key, value in original.shooters.items()
        }
    )

    return {
        "engine": "single_batch_dry_run_v1",
        "status": "SIMULATED" if best else "NO_LEGAL_BATCH",
        "initial_pixels": original.remaining_pixels,
        "accessible_group_count": len(groups),
        "candidates_examined": examined,
        "candidate_limit": max_candidates,
        "search_truncated": truncated,
        "best": best,
        "top_candidates": candidates[:5],
        "source_state_unchanged": unchanged,
        "evidence_verified": False,
        "live_execution_allowed": False,
        "gameplay_actions_performed": False,
        "limitations": [
            "Only one conveyor batch and one abstract conveyor lap are simulated.",
            "Conveyor timing is configurable but not calibrated to live gameplay.",
            "Unverified observations cannot authorize gameplay actions.",
        ],
    }


def _run_multi_batch_schedule_unchecked(state, batches, config=None, allow_storage_reactivation=False):
    """
    Build11R: replay and validate a multi-batch schedule against GameState.

    This is a simulation adapter. Shot counts in batches must come from
    a separate simulation or observation; this function does not fire shots.
    """
    from conveyor_simulator import SimulatorConfig
    from multi_batch_planner import simulate_batch_schedule

    if not isinstance(state, GameState):
        raise TypeError("Expected a GameState")

    if state.validate():
        raise ValueError("GameState validation failed")

    if (hasattr(state, "shooter_capture_provenance_verified")
            and state.shooter_capture_provenance_verified is not True):
        return {
            "simulation_only": True,
            "live_taps_enabled": False,
            "schedule_valid": False,
            "failure_reason": "UNVERIFIED_SHOOTER_CAPTURE_PROVENANCE",
            "batches_completed": 0,
            "batch_reports": [{
                "batch": None,
                "valid": False,
                "reason": "UNVERIFIED_SHOOTER_CAPTURE_PROVENANCE",
            }],
            "groups_scheduled": [],
            "conveyor_occupied": len(state.conveyor),
            "live_execution_allowed": False,
            "gameplay_actions_performed": False,
        }

    if config is None:
        config = SimulatorConfig()
    elif not isinstance(config, SimulatorConfig):
        return {
            "simulation_only": True,
            "live_taps_enabled": False,
            "schedule_valid": False,
            "failure_reason": "CONFIG_MUST_BE_SIMULATOR_CONFIG",
            "batches_completed": 0,
            "batch_reports": [{
                "batch": None,
                "valid": False,
                "reason": "CONFIG_MUST_BE_SIMULATOR_CONFIG",
            }],
            "groups_scheduled": [],
            "conveyor_occupied": len(state.conveyor),
            "live_execution_allowed": False,
            "gameplay_actions_performed": False,
        }

    conveyor_ids = set(state.conveyor)
    storage = getattr(state, "storage", [])

    if isinstance(storage, dict):
        storage_ids = {
            str(value) for value in storage.values()
            if value is not None
        }
        storage_occupied = len(storage_ids)
    else:
        storage_ids = {
            str(value) for value in storage
            if value is not None
        }
        storage_occupied = len(storage_ids)

    records = []

    for shooter_id, shooter in state.shooters.items():
        group_id = state.bonded_group_id(shooter_id)
        if group_id is None:
            raise ValueError("Invalid bonded group identity")

        progress = float(shooter.rotation_progress or 0.0)
        position = round(progress * config.ticks_per_lap)
        position %= config.ticks_per_lap

        records.append({
            "id": str(shooter_id),
            "group_id": group_id,
            "ammo": shooter.ammo,
            "position": position,
            "selected": str(shooter_id) in conveyor_ids,
            "returned": str(shooter_id) in storage_ids,
        })

    report = simulate_batch_schedule(
        records,
        batches,
        storage_occupied=storage_occupied,
        config=config,
        allow_storage_reactivation=allow_storage_reactivation,
    )

    report.update({
        "engine": "build11r_execution_engine_multi_batch",
        "source_state_unchanged": True,
        "existing_conveyor_restored": True,
        "existing_storage_restored": True,
        "rotation_position_calibrated": False,
        "evidence_verified": False,
        "live_execution_allowed": False,
        "gameplay_actions_performed": False,
    })

    return report


# Build11Z: recursive source-state integrity verification.
def _freeze_integrity_value(value, active=None):
    if active is None:
        active = set()

    if value is None or isinstance(value, (bool, int, float, str)):
        return value

    object_id = id(value)
    if object_id in active:
        return ("cycle", type(value).__module__, type(value).__qualname__)

    active.add(object_id)
    try:
        if isinstance(value, dict):
            items = [
                (
                    _freeze_integrity_value(key, active),
                    _freeze_integrity_value(item, active)
                )
                for key, item in value.items()
            ]
            return ("dict", tuple(sorted(items, key=repr)))

        if isinstance(value, (list, tuple)):
            return (
                type(value).__name__,
                tuple(_freeze_integrity_value(item, active) for item in value)
            )

        if isinstance(value, (set, frozenset)):
            items = [_freeze_integrity_value(item, active) for item in value]
            return (type(value).__name__, tuple(sorted(items, key=repr)))

        attributes = getattr(value, "__dict__", None)
        if isinstance(attributes, dict):
            return (
                "object",
                type(value).__module__,
                type(value).__qualname__,
                _freeze_integrity_value(attributes, active)
            )

        return (
            "fallback",
            type(value).__module__,
            type(value).__qualname__,
            repr(value)
        )
    finally:
        active.remove(object_id)


def run_multi_batch_schedule(
    state,
    batches,
    config=None,
    allow_storage_reactivation=False
):
    before = _freeze_integrity_value(state)

    result = _run_multi_batch_schedule_unchecked(
        state,
        batches,
        config=config,
        allow_storage_reactivation=allow_storage_reactivation
    )

    unchanged = before == _freeze_integrity_value(state)

    result["source_state_unchanged"] = unchanged
    result["source_state_integrity_checked"] = True

    if not unchanged:
        result["schedule_valid"] = False
        result["failure_reason"] = "SOURCE_STATE_MUTATED"
        result.setdefault("errors", []).append(
            "Original GameState changed during multi-batch simulation."
        )

    return result
