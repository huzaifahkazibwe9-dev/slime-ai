"""Simulation-only event-driven multi-batch conveyor scheduler."""
from collections.abc import Mapping
import hashlib
import json

from conveyor_simulator import create_simulator, SimulatorConfig
from simulator_snapshot import snapshot_simulator, restore_simulator

CHECKPOINT_SCHEMA_VERSION = 1


def _schedule_fingerprint(records, batches, storage_occupied, config,
                          allow_storage_reactivation):
    try:
        payload = {
            "records": records,
            "batches": [
                dict(batch) if isinstance(batch, Mapping) else batch
                for batch in batches
            ],
            "storage_occupied": storage_occupied,
            "config": {
                "conveyor_capacity": config.conveyor_capacity,
                "storage_capacity": config.storage_capacity,
                "ticks_per_lap": config.ticks_per_lap,
            },
            "allow_storage_reactivation": allow_storage_reactivation,
        }
        encoded = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError("checkpoint schedule must be JSON-compatible") from exc
    return hashlib.sha256(encoded).hexdigest()


def simulate_batch_schedule(
    shooter_records,
    batches,
    storage_occupied=0,
    config=None,
    allow_storage_reactivation=False,
    max_batches=None,
    resume_from=None,
):
    if config is None:
        config = SimulatorConfig()
        config_error = False
    elif not isinstance(config, SimulatorConfig):
        config_error = True
    else:
        config_error = False

    def invalid_input(reason):
        return {
            "simulation_only": True,
            "live_actions_performed": False,
            "live_taps_enabled": False,
            "schedule_valid": False,
            "failure_reason": reason,
            "batches_completed": 0,
            "batch_reports": [{
                "batch": None, "valid": False, "reason": reason,
            }],
            "groups_scheduled": [],
            "conveyor_occupied": 0,
            "storage_occupied": storage_occupied
                if type(storage_occupied) is int and storage_occupied >= 0
                else None,
            "live_execution_allowed": False,
            "gameplay_actions_performed": False,
            "timing_calibrated_to_game": False,
        }

    if config_error:
        return invalid_input("CONFIG_MUST_BE_SIMULATOR_CONFIG")

    if type(allow_storage_reactivation) is not bool:
        return invalid_input("ALLOW_STORAGE_REACTIVATION_MUST_BE_BOOLEAN")
    if max_batches is not None and (
        type(max_batches) is not int or max_batches < 1
    ):
        return invalid_input("MAX_BATCHES_MUST_BE_A_POSITIVE_INTEGER")
    if resume_from is not None and not isinstance(resume_from, dict):
        return invalid_input("CHECKPOINT_MUST_BE_AN_OBJECT")
    if (max_batches is not None or resume_from is not None) and not isinstance(
        batches, (list, tuple)
    ):
        return invalid_input("CHECKPOINT_REQUIRES_A_FINITE_BATCH_SEQUENCE")

    if not isinstance(shooter_records, (list, tuple)):
        return invalid_input("SHOOTER_RECORDS_MUST_BE_A_SEQUENCE")
    records = []
    seen_ids = set()
    for index, item in enumerate(shooter_records):
        if not isinstance(item, Mapping):
            return invalid_input("SHOOTER_RECORD_MUST_BE_A_MAPPING")
        record = dict(item)
        shooter_id = record.get("id")
        group_id = record.get("group_id", shooter_id)
        ammo = record.get("ammo")
        if not isinstance(shooter_id, str) or not shooter_id.strip():
            return invalid_input("SHOOTER_ID_MUST_BE_A_NONEMPTY_STRING")
        if shooter_id in seen_ids:
            return invalid_input("DUPLICATE_SHOOTER_ID")
        seen_ids.add(shooter_id)
        if not isinstance(group_id, str) or not group_id.strip():
            return invalid_input("GROUP_ID_MUST_BE_A_NONEMPTY_STRING")
        if type(ammo) is not int or ammo < 0:
            return invalid_input("SHOOTER_AMMO_MUST_BE_A_NONNEGATIVE_INTEGER")
        for field in ("position", "completed_laps"):
            value = record.get(field, 0)
            if type(value) is not int or value < 0:
                return invalid_input("SHOOTER_POSITION_STATE_MUST_BE_NONNEGATIVE_INTEGER")
        for field in ("selected", "returned"):
            if type(record.get(field, False)) is not bool:
                return invalid_input("SHOOTER_STATE_FLAGS_MUST_BE_BOOLEAN")
        records.append(record)

    try:
        fingerprint = (
            _schedule_fingerprint(
                records, batches, storage_occupied, config,
                allow_storage_reactivation,
            )
            if max_batches is not None or resume_from is not None
            else None
        )
    except ValueError as exc:
        return invalid_input(str(exc))

    if resume_from is None:
        try:
            sim = create_simulator(records, storage_occupied, config)
        except (TypeError, ValueError, KeyError) as exc:
            return invalid_input("INVALID_INITIAL_SIMULATOR_STATE: " + str(exc))
        seen = set()
        reports = []
        start_index = 0
    else:
        try:
            if resume_from.get("schema_version") != CHECKPOINT_SCHEMA_VERSION:
                raise ValueError("unsupported checkpoint schema version")
            if resume_from.get("simulation_only") is not True:
                raise ValueError("checkpoint must be simulation-only")
            if resume_from.get("live_actions_performed") is not False:
                raise ValueError("checkpoint cannot claim live actions")
            if resume_from.get("live_taps_enabled") is not False:
                raise ValueError("checkpoint cannot enable live taps")
            if resume_from.get("schedule_sha256") != fingerprint:
                raise ValueError("checkpoint does not match this schedule")
            start_index = resume_from.get("next_batch_index")
            if type(start_index) is not int or not 0 <= start_index <= len(batches):
                raise ValueError("checkpoint batch index is invalid")
            saved_seen = resume_from.get("seen_groups")
            saved_reports = resume_from.get("batch_reports")
            if (
                not isinstance(saved_seen, list)
                or any(not isinstance(g, str) or not g for g in saved_seen)
                or len(saved_seen) != len(set(saved_seen))
                or not isinstance(saved_reports, list)
                or len(saved_reports) != start_index
                or any(
                    not isinstance(r, dict)
                    or r.get("batch") != i
                    or r.get("valid") is not True
                    for i, r in enumerate(saved_reports)
                )
            ):
                raise ValueError("checkpoint scheduler history is invalid")
            expected_seen = set()
            for report in saved_reports:
                reactivated = report.get("reactivated_groups", [])
                requested = report.get("groups", [])
                if (
                    not isinstance(reactivated, list)
                    or not isinstance(requested, list)
                    or any(not isinstance(g, str) for g in reactivated + requested)
                ):
                    raise ValueError("checkpoint group history is invalid")
                expected_seen.difference_update(reactivated)
                expected_seen.update(requested)
            if set(saved_seen) != expected_seen:
                raise ValueError("checkpoint seen-group state is inconsistent")
            sim = restore_simulator(resume_from.get("simulator_snapshot"))
            if sim.failed:
                raise ValueError("failed simulations cannot be resumed")
            if sim.config != config:
                raise ValueError("checkpoint simulator config does not match")
            if [s.shooter_id for s in sim.shooters] != [
                r["id"] for r in records
            ]:
                raise ValueError("checkpoint shooter roster does not match")
            if [s.group_id for s in sim.shooters] != [
                r.get("group_id", r["id"]) for r in records
            ]:
                raise ValueError("checkpoint shooter groups do not match")
            seen = set(saved_seen)
            reports = [dict(r) for r in saved_reports]
        except (TypeError, ValueError, KeyError) as exc:
            return invalid_input("INVALID_CHECKPOINT: " + str(exc))

    groups = {}
    by_id = {s.shooter_id: s for s in sim.shooters}
    for item in records:
        groups.setdefault(
            str(item.get("group_id", item["id"])), []
        ).append(str(item["id"]))

    for group_id, members in groups.items():
        flags = [by_id[mid].selected for mid in members]
        if any(flags) and not all(flags):
            result = sim.report()
            result.update({
                "schedule_valid": False,
                "failure_reason": "PARTIALLY_RESTORED_BONDED_GROUP",
                "failed_group_id": group_id,
                "batches_completed": 0,
                "batch_reports": [],
                "live_execution_allowed": False,
                "gameplay_actions_performed": False,
            })
            return result

    valid = True

    def snapshot_transition():
        return {
            "shooters": [
                (s.ammo, s.position, s.completed_laps, s.selected, s.returned)
                for s in sim.shooters
            ],
            "storage_occupied": sim.storage_occupied,
            "returned_ids": list(sim.returned_ids),
            "events_length": len(sim.events),
            "seen": set(seen),
        }

    def rollback_transition(snapshot):
        for shooter, values in zip(sim.shooters, snapshot["shooters"]):
            (shooter.ammo, shooter.position, shooter.completed_laps,
             shooter.selected, shooter.returned) = values
        sim.storage_occupied = snapshot["storage_occupied"]
        sim.returned_ids[:] = snapshot["returned_ids"]
        del sim.events[snapshot["events_length"]:]
        seen.clear()
        seen.update(snapshot["seen"])

    try:
        batch_iterator = iter(batches[start_index:])
    except TypeError:
        result = sim.report()
        result.update({
            "engine": "event_driven_multi_batch_scheduler_build11t",
            "schedule_valid": False,
            "batches_completed": 0,
            "batch_reports": [{
                "batch": None,
                "valid": False,
                "reason": "BATCHES_MUST_BE_ITERABLE",
            }],
            "groups_scheduled": [],
            "storage_reactivation_enabled": allow_storage_reactivation,
            "live_execution_allowed": False,
            "gameplay_actions_performed": False,
            "timing_calibrated_to_game": False,
            "limitations": [
                "Shot counts are supplied inputs, not live observations.",
                "Conveyor timing is abstract and uncalibrated.",
                "Storage reactivation is an optional unverified game assumption.",
                "Only fully returned bonded groups can be reactivated.",
                "Board geometry and pixel removal are not simulated.",
            ],
        })
        return result

    index = start_index
    processed_this_call = 0
    stopped_at_limit = False
    while True:
        if max_batches is not None and processed_this_call >= max_batches:
            stopped_at_limit = index < len(batches)
            break
        try:
            batch = next(batch_iterator)
        except StopIteration:
            break
        except Exception as exc:
            valid = False
            reports.append({
                "batch": index,
                "valid": False,
                "reason": "BATCH_ITERATION_FAILED",
                "exception_type": type(exc).__name__,
            })
            break
        def reject(reason, **extra):
            nonlocal valid
            valid = False
            reports.append({
                "batch": index, "valid": False,
                "reason": reason, **extra
            })

        if not isinstance(batch, dict):
            reject("BATCH_MUST_BE_A_MAPPING")
            break
        raw_requested = batch.get("groups", [])
        if not isinstance(raw_requested, (list, tuple)):
            reject("GROUPS_MUST_BE_A_SEQUENCE")
            break
        if any(not isinstance(x, str) or not x.strip()
               for x in raw_requested):
            reject("GROUP_IDS_MUST_BE_NONEMPTY_STRINGS")
            break
        requested = list(raw_requested)

        if not requested or len(requested) != len(set(requested)):
            reject("EMPTY_OR_DUPLICATE_GROUPS_IN_BATCH")
            break

        if any(g not in groups for g in requested):
            reject("UNKNOWN_GROUP_ID")
            break

        raw_reactivate = batch.get("reactivate_groups", [])
        if not isinstance(raw_reactivate, (list, tuple)):
            reject("REACTIVATE_GROUPS_MUST_BE_A_SEQUENCE")
            break
        if any(not isinstance(x, str) or not x.strip()
               for x in raw_reactivate):
            reject("REACTIVATION_GROUP_IDS_MUST_BE_NONEMPTY_STRINGS")
            break
        reactivate = list(raw_reactivate)
        if len(reactivate) != len(set(reactivate)):
            reject("DUPLICATE_REACTIVATION_GROUPS")
            break
        if reactivate and not allow_storage_reactivation:
            reject("STORAGE_REACTIVATION_NOT_ENABLED")
            break
        if any(g not in groups for g in reactivate):
            reject("UNKNOWN_REACTIVATION_GROUP")
            break
        if any(g not in seen for g in reactivate):
            reject("GROUP_NOT_PREVIOUSLY_SCHEDULED")
            break

        # A group may appear in both lists: it is restored from storage
        # and then selected onto the conveyor as part of this same batch.
        overlap = sorted(set(reactivate) & set(requested))
        repeated = sorted(set(requested) & (seen - set(reactivate)))
        if repeated:
            reject("GROUP_SCHEDULED_MORE_THAN_ONCE", group_ids=repeated)
            break
        unavailable = [
            g for g in requested
            if g not in overlap
            and any(by_id[mid].selected for mid in groups[g])
        ]
        if unavailable:
            reject(
                "GROUP_ALREADY_ON_CONVEYOR_OR_RETURNED",
                group_ids=unavailable,
            )
            break

        # Preflight the entire transition before mutating simulator state.
        # Reactivated groups are counted once: their storage-to-conveyor
        # transition and subsequent selection occupy the same physical slots.
        reactivation_slots = 0
        for group_id in reactivate:
            members = groups[group_id]
            if not all(by_id[mid].returned for mid in members):
                reject(
                    "GROUP_NOT_FULLY_RETURNED",
                    group_id=group_id,
                )
                break
            reactivation_slots += len(members)
        if not valid:
            break

        for group_id in reactivate:
            required = len(groups[group_id])
            if required > sim.conveyor_free:
                reject(
                    "INSUFFICIENT_CONVEYOR_SPACE_FOR_REACTIVATION",
                    group_id=group_id,
                    required_slots=required,
                    available_slots=sim.conveyor_free,
                )
                break
        if not valid:
            break

        selection_slots = sum(len(groups[g]) for g in requested)
        overlap_slots = sum(len(groups[g]) for g in overlap)
        total_required_slots = (
            reactivation_slots + selection_slots - overlap_slots
        )
        if total_required_slots > sim.conveyor_free:
            reason = (
                "INSUFFICIENT_CONVEYOR_SPACE_FOR_BATCH_TRANSITION"
                if reactivate else "INSUFFICIENT_CONVEYOR_SPACE"
            )
            reject(
                reason,
                reactivation_slots=reactivation_slots,
                selection_slots=selection_slots,
                required_slots=total_required_slots,
                available_slots=sim.conveyor_free,
            )
            break

        required_storage = reactivation_slots
        if required_storage > sim.storage_occupied:
            reject(
                "INSUFFICIENT_STORAGE_OCCUPANCY_FOR_REACTIVATION",
                required_slots=required_storage,
                available_slots=sim.storage_occupied,
            )
            break

        # Validate shot input for every requested member before any
        # reactivation or selection mutates simulator state.
        shots_map = batch.get("shots", {})
        if not isinstance(shots_map, dict):
            reject("SHOTS_MUST_BE_A_MAPPING")
            break
        requested_members = [
            member for group_id in requested for member in groups[group_id]
        ]
        if any(key not in requested_members for key in shots_map):
            reject("UNKNOWN_SHOOTER_IN_SHOT_MAP")
            break
        invalid_shot = next((
            (member, shots_map.get(member, 0))
            for member in requested_members
            if (
                type(shots_map.get(member, 0)) is not int
                or shots_map.get(member, 0) < 0
                or shots_map.get(member, 0) > by_id[member].ammo
            )
        ), None)
        if invalid_shot is not None:
            reject(
                "INVALID_OR_EXCESSIVE_SHOT_COUNT",
                shooter_id=invalid_shot[0],
            )
            break

        transition_snapshot = snapshot_transition()
        for group_id in reactivate:
            if not sim.reactivate_group(group_id):
                rollback_transition(transition_snapshot)
                reject(
                    "SIMULATOR_REJECTED_STORAGE_REACTIVATION",
                    group_id=group_id,
                )
                break
            seen.remove(group_id)
        if not valid:
            break

        needed = sum(len(groups[g]) for g in requested)
        if needed > sim.conveyor_free:
            rollback_transition(transition_snapshot)
            reject(
                "INSUFFICIENT_CONVEYOR_SPACE",
                required_slots=needed,
                available_slots=sim.conveyor_free,
            )
            break

        # Treat the entire multi-group selection as one transaction.
        selection_ok = True
        for group_id in requested:
            if not sim.select_group(group_id):
                selection_ok = False
                break
        if not selection_ok:
            rollback_transition(transition_snapshot)
            reject("SIMULATOR_REJECTED_GROUP_SELECTION")
            break

        shots_map = batch.get("shots", {})
        if not isinstance(shots_map, dict):
            reject("SHOTS_MUST_BE_A_MAPPING")
            break

        shot_error = False
        for group_id in requested:
            for shooter_id in groups[group_id]:
                shots = shots_map.get(shooter_id, 0)
                if (type(shots) is not int or shots < 0
                        or not sim.record_shots(shooter_id, shots)):
                    shot_error = True
                    break
            if shot_error:
                break

        if shot_error:
            rollback_transition(transition_snapshot)
            reject("INVALID_OR_EXCESSIVE_SHOT_COUNT")
            break

        ticks = 0
        for _ in range(config.ticks_per_lap):
            if sim.failed:
                break
            if ticks and not any(s.ammo == 0 for s in sim.active):
                break
            tick_succeeded = sim.tick(1)
            # Count attempted ticks as well as successful ones: a failing
            # tick advances simulator time before detecting storage overflow.
            ticks += 1
            if not tick_succeeded:
                break
            if not any(s.ammo == 0 for s in sim.active):
                break

        reports.append({
            "batch": index,
            "valid": not sim.failed,
            "reason": sim.failure_reason if sim.failed else None,
            "groups": requested,
            "reactivated_groups": reactivate,
            "ticks_used": ticks,
            "returned_shooters": list(sim.returned_ids),
            "conveyor_occupied": len(sim.active),
            "storage_occupied": sim.storage_occupied,
            "failed": sim.failed,
        })
        seen.update(requested)

        if sim.failed:
            valid = False
            break

        index += 1
        processed_this_call += 1

    checkpoint = None
    if (
        stopped_at_limit and valid and not sim.failed
        and index < len(batches)
    ):
        checkpoint = {
            "schema_version": CHECKPOINT_SCHEMA_VERSION,
            "simulation_only": True,
            "live_taps_enabled": False,
            "live_actions_performed": False,
            "schedule_sha256": fingerprint,
            "next_batch_index": index,
            "seen_groups": sorted(seen),
            "batch_reports": [dict(report) for report in reports],
            "simulator_snapshot": snapshot_simulator(sim),
        }

    result = sim.report()
    result.update({
        "engine": "event_driven_multi_batch_scheduler_build11t",
        "schedule_valid": valid and not sim.failed,
        "schedule_complete": (
            valid and not sim.failed and index >= len(batches)
            if isinstance(batches, (list, tuple))
            else valid and not sim.failed
        ),
        "next_batch_index": index,
        "checkpoint": checkpoint,
        "batches_completed": sum(
            r.get("valid", False) for r in reports
        ),
        "batch_reports": reports,
        "groups_scheduled": sorted(seen),
        "storage_reactivation_enabled": allow_storage_reactivation,
        "live_execution_allowed": False,
        "gameplay_actions_performed": False,
        "timing_calibrated_to_game": False,
        "limitations": [
            "Shot counts are supplied inputs, not live observations.",
            "Conveyor timing is abstract and uncalibrated.",
            "Storage reactivation is an optional unverified game assumption.",
            "Only fully returned bonded groups can be reactivated.",
            "Board geometry and pixel removal are not simulated.",
        ],
    })
    return result
