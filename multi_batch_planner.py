"""Simulation-only event-driven multi-batch conveyor scheduler."""
from collections.abc import Mapping
from conveyor_simulator import create_simulator, SimulatorConfig


def simulate_batch_schedule(
    shooter_records,
    batches,
    storage_occupied=0,
    config=None,
    allow_storage_reactivation=False,
    checkpoint=None,
):
    def invalid_input(reason):
        return {
            "simulation_only": True,
            "live_actions_performed": False,
            "live_taps_enabled": False,
            "schedule_valid": False,
            "failure_reason": reason,
            "batches_completed": 0,
            "batch_reports": [{"batch": None, "valid": False, "reason": reason}],
            "groups_scheduled": [],
            "conveyor_occupied": 0,
            "storage_occupied": storage_occupied
                if type(storage_occupied) is int and storage_occupied >= 0
                else None,
            "live_execution_allowed": False,
            "gameplay_actions_performed": False,
            "timing_calibrated_to_game": False,
        }

    if checkpoint is not None:
        from scheduler_checkpoint import restore_scheduler_checkpoint
        try:
            restored = restore_scheduler_checkpoint(checkpoint)
        except (TypeError, ValueError, KeyError) as exc:
            return invalid_input("INVALID_SCHEDULER_CHECKPOINT: " + str(exc))
        sim = restored["simulator"]
        if config is not None and config != sim.config:
            return invalid_input("CHECKPOINT_CONFIG_MISMATCH")
        allow_storage_reactivation = restored["allow_storage_reactivation"]
        groups = {}
        by_id = {s.shooter_id: s for s in sim.shooters}
        for shooter in sim.shooters:
            groups.setdefault(shooter.group_id, []).append(shooter.shooter_id)
        seen = set(restored["groups_scheduled"])
        reports = restored["completed_batch_reports"]
        index = restored["next_batch_index"]
    else:
        if config is None:
            config = SimulatorConfig()
            config_error = False
        elif not isinstance(config, SimulatorConfig):
            config_error = True
        else:
            config_error = False

        if config_error:
            return invalid_input("CONFIG_MUST_BE_SIMULATOR_CONFIG")
        if type(allow_storage_reactivation) is not bool:
            return invalid_input("ALLOW_STORAGE_REACTIVATION_MUST_BE_BOOLEAN")
        if not isinstance(shooter_records, (list, tuple)):
            return invalid_input("SHOOTER_RECORDS_MUST_BE_A_SEQUENCE")

        records = []
        seen_ids = set()
        for item in shooter_records:
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
            sim = create_simulator(records, storage_occupied, config)
        except (TypeError, ValueError, KeyError) as exc:
            return invalid_input("INVALID_INITIAL_SIMULATOR_STATE: " + str(exc))

        groups = {}
        by_id = {s.shooter_id: s for s in sim.shooters}
        for item in records:
            groups.setdefault(item.get("group_id", item["id"]), []).append(item["id"])

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
        seen = set()
        reports = []
        index = 0

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
        batch_iterator = iter(batches)
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

    while True:
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

    result = sim.report()
    scheduler_checkpoint = None
    if not sim.failed:
        from scheduler_checkpoint import create_scheduler_checkpoint
        successful_reports = [r for r in reports if r.get("valid") is True]
        if len(successful_reports) == index:
            try:
                scheduler_checkpoint = create_scheduler_checkpoint(
                    sim, index, successful_reports, sorted(seen),
                    allow_storage_reactivation=allow_storage_reactivation,
                )
            except (TypeError, ValueError):
                scheduler_checkpoint = None
    result.update({
        "engine": "event_driven_multi_batch_scheduler_build11t",
        "schedule_valid": valid and not sim.failed,
        "batches_completed": sum(
            r.get("valid", False) for r in reports
        ),
        "batch_reports": reports,
        "groups_scheduled": sorted(seen),
        "scheduler_checkpoint": scheduler_checkpoint,
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
