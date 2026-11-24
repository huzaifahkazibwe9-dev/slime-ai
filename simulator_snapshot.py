"""Versioned, validated persistence for the simulation-only conveyor model.

Snapshots preserve simulator state and event ordering. They do not represent
observations from the live game and never enable gameplay actions.
"""
import copy
import json

from conveyor_simulator import (
    ConveyorSimulator, SimulatorConfig, create_simulator,
)

SNAPSHOT_SCHEMA_VERSION = 1


def _require_json_compatible(value):
    """Reject values that JSON cannot preserve without changing their shape."""
    try:
        encoded = json.dumps(value, allow_nan=False)
        decoded = json.loads(encoded)
    except (TypeError, ValueError) as exc:
        raise ValueError("snapshot contains non-JSON-compatible data") from exc
    if decoded != value:
        raise ValueError("snapshot data would change during JSON serialization")


def snapshot_simulator(sim):
    """Return a detached JSON-compatible snapshot of a simulator."""
    if not isinstance(sim, ConveyorSimulator):
        raise ValueError("sim must be a ConveyorSimulator")
    snapshot = {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "simulation_only": True,
        "config": {
            "conveyor_capacity": sim.config.conveyor_capacity,
            "storage_capacity": sim.config.storage_capacity,
            "ticks_per_lap": sim.config.ticks_per_lap,
        },
        "storage_occupied": sim.storage_occupied,
        "tick_count": sim.tick_count,
        "failed": sim.failed,
        "failure_reason": sim.failure_reason,
        "shooters": [
            {
                "id": s.shooter_id,
                "group_id": s.group_id,
                "ammo": s.ammo,
                "position": s.position,
                "completed_laps": s.completed_laps,
                "selected": s.selected,
                "returned": s.returned,
            }
            for s in sim.shooters
        ],
        "returned_ids": list(sim.returned_ids),
        "events": copy.deepcopy(sim.events),
        "live_taps_enabled": False,
        "live_actions_performed": False,
    }
    _require_json_compatible(snapshot)
    return snapshot


def restore_simulator(snapshot):
    """Restore a snapshot, rejecting malformed or internally inconsistent data."""
    if not isinstance(snapshot, dict):
        raise ValueError("snapshot must be an object")
    _require_json_compatible(snapshot)
    if snapshot.get("schema_version") != SNAPSHOT_SCHEMA_VERSION:
        raise ValueError("unsupported snapshot schema version")
    if snapshot.get("simulation_only") is not True:
        raise ValueError("snapshot must be explicitly simulation-only")
    if snapshot.get("live_taps_enabled") is not False:
        raise ValueError("snapshot cannot enable live taps")
    if snapshot.get("live_actions_performed") is not False:
        raise ValueError("snapshot cannot claim live actions")

    config_data = snapshot.get("config")
    if not isinstance(config_data, dict):
        raise ValueError("config must be an object")
    try:
        config = SimulatorConfig(**config_data)
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid snapshot config: " + str(exc)) from exc

    shooters = snapshot.get("shooters")
    if not isinstance(shooters, list) or not shooters:
        raise ValueError("shooters must be a non-empty list")
    if any(not isinstance(item, dict) for item in shooters):
        raise ValueError("each shooter record must be an object")
    # The simulator retains selected=True as historical state after return.
    # Active conveyor membership is selected and not returned, so both flags
    # may legitimately be true in a completed shooter record.
    try:
        sim = create_simulator(
            shooters,
            storage_occupied=snapshot.get("storage_occupied"),
            config=config,
        )
    except (TypeError, ValueError, KeyError) as exc:
        raise ValueError("invalid restored shooter state: " + str(exc)) from exc

    tick_count = snapshot.get("tick_count")
    if type(tick_count) is not int or tick_count < 0:
        raise ValueError("tick_count must be a non-negative integer")

    failed = snapshot.get("failed")
    failure_reason = snapshot.get("failure_reason")
    if type(failed) is not bool:
        raise ValueError("failed must be a boolean")
    if not isinstance(failure_reason, str):
        raise ValueError("failure_reason must be a string")
    if failed != bool(failure_reason.strip()):
        raise ValueError("failed and failure_reason are inconsistent")

    events = snapshot.get("events")
    if not isinstance(events, list):
        raise ValueError("events must be a list")
    previous_tick = -1
    for event in events:
        if not isinstance(event, dict):
            raise ValueError("each event must be an object")
        event_tick = event.get("tick")
        event_type = event.get("event")
        if (type(event_tick) is not int or not 0 <= event_tick <= tick_count
                or event_tick < previous_tick
                or not isinstance(event_type, str) or not event_type.strip()):
            raise ValueError("event has invalid or out-of-order tick/type")
        previous_tick = event_tick
    if not failed and events and events[-1].get("event") == "LEVEL_FAILURE":
        raise ValueError("non-failed snapshot cannot end with LEVEL_FAILURE")

    returned_ids = snapshot.get("returned_ids")
    if not isinstance(returned_ids, list) or any(
        not isinstance(value, str) for value in returned_ids
    ):
        raise ValueError("returned_ids must be a list of strings")
    returned_from_shooters = {
        shooter.shooter_id for shooter in sim.shooters if shooter.returned
    }
    if (len(returned_ids) != len(set(returned_ids))
            or set(returned_ids) != returned_from_shooters):
        raise ValueError("returned_ids do not match returned shooter flags")

    known_shooter_ids = {shooter.shooter_id for shooter in sim.shooters}
    event_return_ids = []
    for event in events:
        shooter_id = event.get("shooter_id")
        if shooter_id is not None and (
            not isinstance(shooter_id, str)
            or shooter_id not in known_shooter_ids
        ):
            raise ValueError("event references an unknown shooter")
        if event.get("event") == "SHOOTER_RETURNED_TO_STORAGE":
            if not isinstance(shooter_id, str):
                raise ValueError("return event must identify its shooter")
            event_return_ids.append(shooter_id)
        members = event.get("members")
        if members is not None and (
            not isinstance(members, list)
            or any(
                not isinstance(member, str) or member not in known_shooter_ids
                for member in members
            )
        ):
            raise ValueError("event contains unknown group members")
    if (len(event_return_ids) != len(set(event_return_ids))
            or any(
                event_return_ids[index] not in returned_ids
                for index in range(len(event_return_ids))
            )
            or [
                shooter_id for shooter_id in returned_ids
                if shooter_id in set(event_return_ids)
            ] != event_return_ids):
        raise ValueError("return event order conflicts with returned_ids")

    if failed and (not events or events[-1].get("event") != "LEVEL_FAILURE"):
        raise ValueError("failed snapshot must end with a LEVEL_FAILURE event")
    if failed and events[-1].get("reason") != failure_reason:
        raise ValueError("failure event reason does not match simulator state")

    sim.tick_count = tick_count
    sim.failed = failed
    sim.failure_reason = failure_reason
    sim.events = copy.deepcopy(events)
    sim.returned_ids = list(returned_ids)
    return sim
