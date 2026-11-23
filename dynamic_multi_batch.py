"""Build11AE: dynamic board simulation connected to multi-batch scheduling."""
import copy

from game_state import GameState
from bonded_group_simulator import simulate_bonded_group
from execution_engine import run_multi_batch_schedule
from conveyor_simulator import SimulatorConfig
from accessibility_utils import normalize_accessible_ids


def _group_index(state):
    result = {}
    for shooter_id in state.shooters:
        group_id = state.bonded_group_id(shooter_id)
        members = state.bonded_group(shooter_id)
        if group_id is not None and members:
            result[group_id] = min(members)
    return result


def simulate_dynamic_multi_batch(
    state,
    batches,
    config=None,
    allow_storage_reactivation=False,
    accessibility_resolver=None,
):
    """Calculate each group's shots on the evolving board, then validate
    the resulting batches with the conveyor scheduler.
    """
    if not isinstance(state, GameState):
        raise TypeError("Expected a GameState")
    errors = state.validate()
    if errors:
        raise ValueError("Invalid GameState: " + "; ".join(errors))
    if not isinstance(batches, list):
        raise TypeError("batches must be a list")
    if accessibility_resolver is not None and not callable(accessibility_resolver):
        raise TypeError("accessibility_resolver must be callable")

    # This build cannot yet model a returned shooter becoming selectable
    # again while also preserving its evolving board and ammunition state.
    if any(
        isinstance(batch, dict) and batch.get("reactivate_groups")
        for batch in batches
    ):
        return {
            "engine": "build11ae_dynamic_multi_batch",
            "status": "SIMULATION_INCOMPLETE",
            "schedule_valid": False,
            "failure": {
                "reason": "DYNAMIC_STORAGE_REACTIVATION_NOT_SUPPORTED",
            },
            "source_state_unchanged": True,
            "source_state_integrity_checked": True,
            "evidence_verified": False,
            "live_execution_allowed": False,
            "gameplay_actions_performed": False,
            "game_taps_enabled": False,
        }

    config = config or SimulatorConfig()
    original = copy.deepcopy(state)
    working = copy.deepcopy(state)
    group_roots = _group_index(state)
    prepared_batches = []
    group_reports = []
    board_history = []
    failure = None

    for batch_index, batch in enumerate(batches):
        if not isinstance(batch, dict):
            failure = {
                "reason": "BATCH_MUST_BE_A_MAPPING",
                "batch": batch_index,
            }
            break

        requested = batch.get("groups", [])
        if not isinstance(requested, list) or not requested:
            failure = {
                "reason": "EMPTY_OR_INVALID_GROUP_LIST",
                "batch": batch_index,
            }
            break

        # Sample accessibility once at batch start. Newly exposed groups
        # cannot become selectable until the next batch boundary.
        batch_accessible = None
        if accessibility_resolver is not None:
            observed = accessibility_resolver(copy.deepcopy(working))
            batch_accessible = normalize_accessible_ids(observed)

        calculated_shots = {}
        for group_id in requested:
            group_id = str(group_id)
            root = group_roots.get(group_id)
            if root is None:
                failure = {
                    "reason": "UNKNOWN_GROUP_ID",
                    "batch": batch_index,
                    "group_id": group_id,
                }
                break

            # The conveyor scheduler independently checks capacity and
            # batch legality. This isolated copy is used only for board math.
            isolated = copy.deepcopy(working)
            isolated.conveyor = []
            isolated.storage = []
            if batch_accessible is not None:
                group_members = isolated.bonded_group(root)
                if not group_members or not set(group_members).issubset(batch_accessible):
                    failure = {
                        "reason": "GROUP_NOT_ACCESSIBLE_AT_BATCH_START",
                        "batch": batch_index,
                        "group_id": group_id,
                        "required_shooter_ids": group_members,
                        "accessible_shooter_ids": sorted(batch_accessible),
                    }
                    break
                for shooter_id, shooter in isolated.shooters.items():
                    shooter.accessible = str(shooter_id) in batch_accessible

            group_report = simulate_bonded_group(isolated, root)
            if group_report.get("status") != "SIMULATED":
                failure = {
                    "reason": "DYNAMIC_GROUP_SIMULATION_FAILED",
                    "batch": batch_index,
                    "group_id": group_id,
                    "group_status": group_report.get("status"),
                }
                break

            member_shots = {}
            for member in group_report["member_reports"]:
                shooter_id = member["shooter_id"]
                member_shots[shooter_id] = member["shots_attempted"]

            calculated_shots.update(member_shots)
            working.board = copy.deepcopy(group_report["final_board"])

            for shooter_id, ammo in group_report["remaining_ammo"].items():
                working.shooters[shooter_id].ammo = ammo
                working.shooters[shooter_id].accessible = False

            group_reports.append({
                "batch": batch_index,
                "group_id": group_id,
                "shooter_ids": list(group_report["shooter_ids"]),
                "shots": member_shots,
                "pixels_removed": group_report["pixels_removed"],
                "remaining_pixels": group_report["remaining_pixels"],
                "dynamic_regions_rebuilt": group_report[
                    "dynamic_regions_rebuilt"
                ],
            })
            board_history.append({
                "after_batch": batch_index,
                "after_group": group_id,
                "remaining_pixels": working.remaining_pixels,
                "board": copy.deepcopy(working.board),
            })

        if failure:
            break

        prepared_batches.append({
            "groups": [str(group) for group in requested],
            "shots": calculated_shots,
            "reactivate_groups": list(
                batch.get("reactivate_groups", [])
            ),
        })

    if failure:
        return {
            "engine": "build11ae_dynamic_multi_batch",
            "status": "SIMULATION_INCOMPLETE",
            "schedule_valid": False,
            "failure": failure,
            "group_simulations": group_reports,
            "board_history": board_history,
            "source_state_unchanged": state == original,
            "source_state_integrity_checked": True,
            "evidence_verified": False,
            "live_execution_allowed": False,
            "gameplay_actions_performed": False,
            "game_taps_enabled": False,
        }

    schedule = run_multi_batch_schedule(
        state,
        prepared_batches,
        config=config,
        allow_storage_reactivation=allow_storage_reactivation,
    )

    unchanged = state == original
    return {
        "engine": "build11ae_dynamic_multi_batch",
        "status": (
            "SIMULATED"
            if schedule.get("schedule_valid")
            else "SCHEDULE_REJECTED"
        ),
        "schedule_valid": schedule.get("schedule_valid", False),
        "prepared_batches": prepared_batches,
        "scheduler_report": schedule,
        "group_simulations": group_reports,
        "board_history": board_history,
        "initial_pixels": original.remaining_pixels,
        "simulated_remaining_pixels": working.remaining_pixels,
        "simulated_pixels_removed": (
            original.remaining_pixels - working.remaining_pixels
        ),
        "source_state_unchanged": unchanged,
        "source_state_integrity_checked": True,
        "evidence_verified": False,
        "live_execution_allowed": False,
        "gameplay_actions_performed": False,
        "game_taps_enabled": False,
        "dynamic_accessibility_resolver_used": accessibility_resolver is not None,
        "limitations": [
            "Board shots are calculated from the current simulated board.",
            "Accessibility is sampled once at each batch start; newly exposed groups require a later batch.",
            "Resolver output is an explicit simulation assumption, not verified gameplay evidence.",
            "Conveyor timing remains abstract and uncalibrated.",
            "Storage reactivation remains unverified and disabled by default.",
            "No screenshot observations or live game actions are performed.",
        ],
    }
