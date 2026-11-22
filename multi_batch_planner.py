"""Simulation-only event-driven multi-batch conveyor scheduler."""
from conveyor_simulator import create_simulator, SimulatorConfig


def simulate_batch_schedule(
    shooter_records,
    batches,
    storage_occupied=0,
    config=None,
    allow_storage_reactivation=False,
):
    config = config or SimulatorConfig()
    records = [dict(item) for item in shooter_records]
    sim = create_simulator(records, storage_occupied, config)

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

    seen = set()
    reports = []
    valid = True

    for index, batch in enumerate(batches):
        requested = [str(x) for x in batch.get("groups", [])]

        def reject(reason, **extra):
            nonlocal valid
            valid = False
            reports.append({
                "batch": index, "valid": False,
                "reason": reason, **extra
            })

        if not requested or len(requested) != len(set(requested)):
            reject("EMPTY_OR_DUPLICATE_GROUPS_IN_BATCH")
            break

        if any(g not in groups for g in requested):
            reject("UNKNOWN_GROUP_ID")
            break

        reactivate = [
            str(x) for x in batch.get("reactivate_groups", [])
        ]
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

        # Preflight all reactivations before changing simulator state.
        for group_id in reactivate:
            members = groups[group_id]
            if not all(by_id[mid].returned for mid in members):
                reject(
                    "GROUP_NOT_FULLY_RETURNED",
                    group_id=group_id,
                )
                break
            if len(members) > sim.conveyor_free:
                reject(
                    "INSUFFICIENT_CONVEYOR_SPACE_FOR_REACTIVATION",
                    group_id=group_id,
                    required_slots=len(members),
                    available_slots=sim.conveyor_free,
                )
                break
        if not valid:
            break

        for group_id in reactivate:
            if not sim.reactivate_group(group_id):
                reject(
                    "SIMULATOR_REJECTED_STORAGE_REACTIVATION",
                    group_id=group_id,
                )
                break
            seen.remove(group_id)
        if not valid:
            break

        if any(g in seen for g in requested):
            reject("GROUP_SCHEDULED_MORE_THAN_ONCE")
            break
        if any(any(by_id[mid].selected for mid in groups[g])
               for g in requested):
            reject("GROUP_ALREADY_ON_CONVEYOR_OR_RETURNED")
            break

        needed = sum(len(groups[g]) for g in requested)
        if needed > sim.conveyor_free:
            reject(
                "INSUFFICIENT_CONVEYOR_SPACE",
                required_slots=needed,
                available_slots=sim.conveyor_free,
            )
            break

        # Validate all groups before selecting any.
        if not all(sim.select_group(g) for g in requested):
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
            reject("INVALID_OR_EXCESSIVE_SHOT_COUNT")
            break

        ticks = 0
        for _ in range(config.ticks_per_lap):
            if sim.failed:
                break
            if ticks and not any(s.ammo == 0 for s in sim.active):
                break
            if not sim.tick(1):
                break
            ticks += 1
            if not any(s.ammo == 0 for s in sim.active):
                break

        reports.append({
            "batch": index,
            "valid": True,
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

    result = sim.report()
    result.update({
        "engine": "event_driven_multi_batch_scheduler_build11t",
        "schedule_valid": valid and not sim.failed,
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
