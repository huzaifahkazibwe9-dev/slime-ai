"""Versioned, validated persistence for the simulation-only conveyor model.

Snapshots preserve simulator state and event ordering. They do not represent
observations from the live game and never enable gameplay actions.
"""
import copy
import json
from strict_json import strict_json_loads
from conveyor_simulator import (
    ConveyorSimulator, SimulatorConfig, create_simulator,
)

SNAPSHOT_SCHEMA_VERSION = 2

# Schema-v2 snapshots only accept events emitted by this simulator version.
# A new event kind requires an explicit schema/validator update rather than
# being silently accepted as an opaque history record.
SUPPORTED_EVENT_TYPES = frozenset({
    "AMMO_UPDATED",
    "GROUP_REACTIVATED_FROM_STORAGE",
    "LEVEL_FAILURE",
    "SELECTION_REJECTED",
    "SHOOTER_COMPLETED",
    "SHOOTER_CONTINUES_ROTATING",
    "SHOOTER_ENTERED",
    "SHOOTER_RETURNED_TO_STORAGE",
    "SHOOTER_ROTATED",
    "SHOOTER_WAITING_FOR_BONDED_GROUP",
    "SHOT_RECORD_REJECTED",
    "STORAGE_REACTIVATION_REJECTED",
})


def _require_json_compatible(value):
    """Reject values that JSON cannot preserve without changing their shape."""
    try:
        encoded = json.dumps(value, allow_nan=False)
        decoded = strict_json_loads(encoded)
    except (TypeError, ValueError) as exc:
        raise ValueError("snapshot contains non-JSON-compatible data") from exc
    if decoded != value:
        raise ValueError("snapshot data would change during JSON serialization")


def _validate_event_payload(event, config, shooter_by_id, group_members_by_id):
    """Validate the versioned payload schema for one simulator event."""
    event_type = event["event"]
    schemas = {
        "AMMO_UPDATED": ({"shooter_id", "shots_recorded", "ammo_remaining"}, set()),
        "GROUP_REACTIVATED_FROM_STORAGE": (
            {"group_id", "members", "storage_occupied"}, set()
        ),
        "LEVEL_FAILURE": ({"reason"}, set()),
        "SELECTION_REJECTED": (
            {"group_id", "reason"}, {"group_size", "free_slots"}
        ),
        "SHOOTER_COMPLETED": ({"shooter_id"}, set()),
        "SHOOTER_CONTINUES_ROTATING": (
            {"shooter_id", "laps", "ammo_remaining"}, set()
        ),
        "SHOOTER_ENTERED": ({"shooter_id", "group_id", "position"}, set()),
        "SHOOTER_RETURNED_TO_STORAGE": (
            {"shooter_id", "storage_occupied", "storage_free"}, set()
        ),
        "SHOOTER_ROTATED": ({"shooter_id", "position"}, set()),
        "SHOOTER_WAITING_FOR_BONDED_GROUP": (
            {"shooter_id", "group_id"}, set()
        ),
        "SHOT_RECORD_REJECTED": (
            {"shooter_id", "requested", "ammo"}, set()
        ),
        "STORAGE_REACTIVATION_REJECTED": ({"group_id", "reason"}, set()),
    }
    required, optional = schemas[event_type]
    allowed = {"tick", "event"} | required | optional
    missing = required - set(event)
    unexpected = set(event) - allowed
    if missing:
        raise ValueError(
            event_type + " event is missing required fields: "
            + ", ".join(sorted(missing))
        )
    if unexpected:
        raise ValueError(
            event_type + " event contains unsupported fields: "
            + ", ".join(sorted(unexpected))
        )

    def require_string(field):
        value = event[field]
        if not isinstance(value, str) or not value.strip():
            raise ValueError(event_type + " event has invalid " + field)

    def require_integer(field, minimum=0):
        value = event[field]
        if type(value) is not int or value < minimum:
            raise ValueError(event_type + " event has invalid " + field)

    if "shooter_id" in required:
        require_string("shooter_id")
        shooter = shooter_by_id.get(event["shooter_id"])
        if shooter is None:
            raise ValueError("event references an unknown shooter")
    else:
        shooter = None

    for field in ("group_id", "reason"):
        if field in required:
            require_string(field)

    if event_type in {
        "SHOOTER_ENTERED", "SHOOTER_WAITING_FOR_BONDED_GROUP"
    } and event["group_id"] != shooter.group_id:
        raise ValueError(event_type + " event group does not match shooter")

    if event_type in {"SHOOTER_ENTERED", "SHOOTER_ROTATED"}:
        require_integer("position")
        if event["position"] >= config.ticks_per_lap:
            raise ValueError(event_type + " event position is outside the lap")

    if event_type == "AMMO_UPDATED":
        require_integer("shots_recorded")
        require_integer("ammo_remaining")
    elif event_type == "GROUP_REACTIVATED_FROM_STORAGE":
        members = event["members"]
        if (not isinstance(members, list) or not members
                or any(not isinstance(member, str) or not member.strip()
                       for member in members)
                or len(members) != len(set(members))):
            raise ValueError(
                "reactivation event must list its group members as unique non-empty strings"
            )
        if set(members) != group_members_by_id.get(event["group_id"], set()):
            raise ValueError("reactivation event must contain the complete group")
        require_integer("storage_occupied")
        if event["storage_occupied"] > config.storage_capacity:
            raise ValueError("reactivation event storage occupancy is out of range")
    elif event_type == "SELECTION_REJECTED":
        present = {"group_size", "free_slots"} & set(event)
        if present and present != {"group_size", "free_slots"}:
            raise ValueError("selection rejection capacity fields must appear together")
        if present:
            require_integer("group_size", 1)
            require_integer("free_slots")
            if event["group_size"] <= event["free_slots"]:
                raise ValueError("selection rejection capacity values are inconsistent")
    elif event_type == "SHOOTER_CONTINUES_ROTATING":
        require_integer("laps", 1)
        require_integer("ammo_remaining", 1)
    elif event_type == "SHOOTER_RETURNED_TO_STORAGE":
        if (type(event["storage_occupied"]) is not int
                or event["storage_occupied"] < 1):
            raise ValueError("invalid storage occupancy in return event")
        if (type(event["storage_free"]) is not int
                or event["storage_free"] < 0):
            raise ValueError("return event storage_free is inconsistent")
    elif event_type == "SHOT_RECORD_REJECTED":
        require_integer("requested")
        require_integer("ammo")
        if event["requested"] <= event["ammo"]:
            raise ValueError("rejected shot count must exceed available ammunition")


def _validate_ammo_event_history(events, shooter_by_id):
    """Replay ammunition events and reconcile them with restored shooter state.

    The initial ammunition for each shooter is inferred from its saved remaining
    ammunition plus all successfully recorded shots. Every intermediate event
    must then agree with that reconstructed history.
    """
    recorded_shots = {shooter_id: 0 for shooter_id in shooter_by_id}
    for event in events:
        if event["event"] == "AMMO_UPDATED":
            recorded_shots[event["shooter_id"]] += event["shots_recorded"]

    ammo_by_id = {
        shooter_id: shooter.ammo + recorded_shots[shooter_id]
        for shooter_id, shooter in shooter_by_id.items()
    }

    for event in events:
        event_type = event["event"]
        shooter_id = event.get("shooter_id")
        if event_type == "AMMO_UPDATED":
            available = ammo_by_id[shooter_id]
            shots = event["shots_recorded"]
            if shots > available:
                raise ValueError(
                    "ammunition history records more shots than were available"
                )
            expected_remaining = available - shots
            if event["ammo_remaining"] != expected_remaining:
                raise ValueError(
                    "ammunition history does not match recorded remaining ammunition"
                )
            ammo_by_id[shooter_id] = expected_remaining
        elif event_type == "SHOT_RECORD_REJECTED":
            if event["ammo"] != ammo_by_id[shooter_id]:
                raise ValueError(
                    "rejected shot event ammunition disagrees with prior history"
                )
        elif event_type == "SHOOTER_CONTINUES_ROTATING":
            if event["ammo_remaining"] != ammo_by_id[shooter_id]:
                raise ValueError(
                    "continuation event ammunition disagrees with prior history"
                )
        elif event_type == "SHOOTER_COMPLETED":
            if ammo_by_id[shooter_id] != 0:
                raise ValueError(
                    "shooter completion event requires zero remaining ammunition"
                )
        elif event_type == "SHOOTER_WAITING_FOR_BONDED_GROUP":
            if ammo_by_id[shooter_id] != 0:
                raise ValueError(
                    "waiting event requires zero remaining ammunition"
                )
        elif event_type == "SHOOTER_RETURNED_TO_STORAGE":
            if ammo_by_id[shooter_id] != 0:
                raise ValueError(
                    "return event requires zero remaining ammunition"
                )


def _validate_return_point_event_history(events):
    """Require each lap-arrival event to follow that shooter's zero-position rotation."""
    rotated_to_return = set()
    resolved_arrivals = set()
    arrival_events = {
        "SHOOTER_CONTINUES_ROTATING",
        "SHOOTER_WAITING_FOR_BONDED_GROUP",
        "SHOOTER_RETURNED_TO_STORAGE",
    }

    for event in events:
        event_type = event["event"]
        key = (event["tick"], event.get("shooter_id"))

        if event_type == "SHOOTER_ROTATED" and event["position"] == 0:
            rotated_to_return.add(key)
            continue

        if event_type not in arrival_events:
            continue

        if key not in rotated_to_return:
            raise ValueError(
                "arrival event must follow a same-tick rotation to the return point"
            )
        if key in resolved_arrivals:
            raise ValueError(
                "shooter has duplicate return-point arrival resolution events"
            )
        resolved_arrivals.add(key)


def _validate_rotation_and_lap_history(events, config, shooter_by_id):
    """Reconcile rotation positions and completed-lap counters with event order."""
    last_position = {}
    last_rotation_tick = {}
    last_laps = {}
    lap_history_known = set()
    final_position_known = set()
    final_laps_known = set()

    for event in events:
        event_type = event["event"]

        if event_type == "SHOOTER_ENTERED":
            shooter_id = event["shooter_id"]
            last_position[shooter_id] = 0
            final_position_known.add(shooter_id)
            last_rotation_tick.pop(shooter_id, None)

        elif event_type == "GROUP_REACTIVATED_FROM_STORAGE":
            for shooter_id in event["members"]:
                last_position[shooter_id] = 0
                final_position_known.add(shooter_id)
                last_rotation_tick.pop(shooter_id, None)
                last_laps[shooter_id] = 0
                lap_history_known.add(shooter_id)
                final_laps_known.add(shooter_id)

        elif event_type == "SHOOTER_ROTATED":
            shooter_id = event["shooter_id"]
            position = event["position"]
            previous_position = last_position.get(shooter_id)
            previous_tick = last_rotation_tick.get(shooter_id)

            if previous_tick is not None and event["tick"] != previous_tick + 1:
                raise ValueError(
                    "active shooter rotation history has a missing or repeated tick"
                )

            if previous_position is not None:
                expected_position = (
                    previous_position + 1
                ) % config.ticks_per_lap
                if position != expected_position:
                    raise ValueError(
                        "rotation history does not advance exactly one position"
                    )

            last_position[shooter_id] = position
            last_rotation_tick[shooter_id] = event["tick"]
            final_position_known.add(shooter_id)

        elif event_type == "SHOOTER_CONTINUES_ROTATING":
            shooter_id = event["shooter_id"]
            laps = event["laps"]
            if shooter_id in last_laps and laps != last_laps[shooter_id] + 1:
                raise ValueError(
                    "completed lap history must increase by exactly one"
                )
            last_laps[shooter_id] = laps
            lap_history_known.add(shooter_id)
            final_laps_known.add(shooter_id)

    for shooter_id in final_position_known:
        if shooter_by_id[shooter_id].position != last_position[shooter_id]:
            raise ValueError(
                "restored shooter position disagrees with rotation event history"
            )

    for shooter_id in final_laps_known:
        if shooter_by_id[shooter_id].completed_laps != last_laps[shooter_id]:
            raise ValueError(
                "restored completed-lap count disagrees with event history"
            )


def _validate_group_entry_event_history(events, group_members_by_id):
    """Require each recorded bonded-group selection to enter atomically."""
    entry_batches = {}
    last_entry_index = {}
    last_reactivation_index = {}

    for event_index, event in enumerate(events):
        event_type = event["event"]

        if event_type == "GROUP_REACTIVATED_FROM_STORAGE":
            group_id = event["group_id"]
            last_reactivation_index[group_id] = event_index
            continue

        if event_type != "SHOOTER_ENTERED":
            continue

        shooter_id = event["shooter_id"]
        group_id = event["group_id"]
        if group_id not in group_members_by_id:
            raise ValueError("entry event references an unknown group")

        if last_entry_index.get(group_id, -1) > last_reactivation_index.get(group_id, -1):
            raise ValueError(
                "bonded group has a new entry without an intervening storage reactivation"
            )
        last_entry_index[group_id] = event_index

        key = (group_id, event["tick"])
        batch = entry_batches.setdefault(key, set())
        if shooter_id in batch:
            raise ValueError(
                "bonded group entry batch contains a duplicate shooter"
            )
        batch.add(shooter_id)

    for (group_id, tick), entered_ids in entry_batches.items():
        expected_ids = group_members_by_id[group_id]
        if entered_ids != expected_ids:
            raise ValueError(
                "bonded group entry must include every member in the same tick"
            )


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
        "initial_storage_occupied": sim.initial_storage_occupied,
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
                "observation_quality": copy.deepcopy(s.observation_quality),
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
    if (type(snapshot.get("schema_version")) is not int
            or snapshot.get("schema_version") != SNAPSHOT_SCHEMA_VERSION):
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

    shooter_by_id = {shooter.shooter_id: shooter for shooter in sim.shooters}
    group_members_by_id = {}
    for shooter in sim.shooters:
        group_members_by_id.setdefault(shooter.group_id, set()).add(
            shooter.shooter_id
        )

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
        if event_type not in SUPPORTED_EVENT_TYPES:
            raise ValueError("snapshot contains an unsupported event type")
        _validate_event_payload(
            event, config, shooter_by_id, group_members_by_id
        )
        previous_tick = event_tick

    _validate_ammo_event_history(events, shooter_by_id)

    failure_event_indices = [
        index for index, event in enumerate(events)
        if event.get("event") == "LEVEL_FAILURE"
    ]
    if failed:
        if (len(failure_event_indices) != 1
                or failure_event_indices[0] != len(events) - 1):
            raise ValueError(
                "failed snapshot must contain exactly one final LEVEL_FAILURE event"
            )
    elif failure_event_indices:
        raise ValueError(
            "non-failed snapshot cannot contain a LEVEL_FAILURE event"
        )

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

    known_shooter_ids = set(shooter_by_id)
    shooter_group_by_id = {
        shooter.shooter_id: shooter.group_id for shooter in sim.shooters
    }
    initial_storage = snapshot.get("initial_storage_occupied")
    if (type(initial_storage) is not int
            or not 0 <= initial_storage <= config.storage_capacity):
        raise ValueError("initial storage occupancy history is invalid")
    sim.initial_storage_occupied = initial_storage
    replayed_occupancy = initial_storage
    occupancy_event_count = 0
    for event in events:
        event_type = event.get("event")
        changes_storage = event_type in {
            "SHOOTER_RETURNED_TO_STORAGE",
            "GROUP_REACTIVATED_FROM_STORAGE",
        }
        if "storage_occupied" in event and not changes_storage:
            raise ValueError("non-storage event cannot change storage occupancy")
        if not changes_storage:
            continue
        if event_type == "SHOOTER_RETURNED_TO_STORAGE":
            replayed_occupancy += 1
        else:
            members = event.get("members")
            if not isinstance(members, list) or not members:
                raise ValueError(
                    "reactivation event must list its group members"
                )
            replayed_occupancy -= len(members)
        if not 0 <= replayed_occupancy <= config.storage_capacity:
            raise ValueError("storage occupancy event delta is out of range")
        occupancy = event.get("storage_occupied")
        if type(occupancy) is not int:
            raise ValueError("event has invalid storage occupancy")
        if occupancy != replayed_occupancy:
            raise ValueError("storage occupancy event delta is inconsistent")
        if event_type == "SHOOTER_RETURNED_TO_STORAGE":
            storage_free = event.get("storage_free")
            if (type(storage_free) is not int
                    or storage_free != config.storage_capacity - replayed_occupancy):
                raise ValueError("return event storage_free is inconsistent")
        occupancy_event_count += 1
    if occupancy_event_count and replayed_occupancy != sim.storage_occupied:
        raise ValueError("latest storage event disagrees with restored occupancy")
    if not occupancy_event_count and initial_storage != sim.storage_occupied:
        raise ValueError("storage occupancy changed without a storage event")

    latest_return_index = {}
    latest_reactivation_index = {}
    for event_index, event in enumerate(events):
        shooter_id = event.get("shooter_id")
        if shooter_id is not None and (
            not isinstance(shooter_id, str)
            or shooter_id not in known_shooter_ids
        ):
            raise ValueError("event references an unknown shooter")
        members = event.get("members")
        if members is not None and (
            not isinstance(members, list)
            or any(
                not isinstance(member, str) or member not in known_shooter_ids
                for member in members
            )
        ):
            raise ValueError("event contains unknown group members")
        if event.get("event") == "SHOOTER_RETURNED_TO_STORAGE":
            if not isinstance(shooter_id, str):
                raise ValueError("return event must identify its shooter")
            latest_return_index[shooter_id] = event_index
        if event.get("event") == "GROUP_REACTIVATED_FROM_STORAGE":
            group_id = event.get("group_id")
            if not isinstance(group_id, str) or not group_id:
                raise ValueError("reactivation event must identify its group")
            if not isinstance(members, list) or not members:
                raise ValueError("reactivation event must list its group members")
            if len(members) != len(set(members)):
                raise ValueError("reactivation event contains duplicate members")
            if set(members) != group_members_by_id.get(group_id, set()):
                raise ValueError("reactivation event must contain the complete group")
            if any(shooter_group_by_id[member] != group_id for member in members):
                raise ValueError("reactivation event group membership is inconsistent")
            for member in members:
                latest_reactivation_index[member] = event_index

    # Validate every recorded return cycle, not just the current state.
    # Bonded members enter storage together; a reactivation starts a new cycle.
    pending_group_returns = {}
    for event in events:
        event_type = event.get("event")
        if event_type == "SHOOTER_RETURNED_TO_STORAGE":
            shooter_id = event["shooter_id"]
            group_id = shooter_group_by_id[shooter_id]
            member_ids = group_members_by_id[group_id]
            pending = pending_group_returns.setdefault(group_id, {})
            if shooter_id in pending:
                raise ValueError("bonded group has duplicate return event")
            pending[shooter_id] = event["tick"]
            if len(pending) == len(member_ids):
                if len(set(pending.values())) != 1:
                    raise ValueError("bonded group return events must share a tick")
            elif len(pending) > len(member_ids):
                raise ValueError("bonded group return history is invalid")
        elif event_type == "GROUP_REACTIVATED_FROM_STORAGE":
            group_id = event["group_id"]
            pending = pending_group_returns.get(group_id, {})
            if pending and set(pending) != group_members_by_id[group_id]:
                raise ValueError("bonded group return history is incomplete")
            pending_group_returns[group_id] = {}

    for group_id, pending in pending_group_returns.items():
        if pending and set(pending) != group_members_by_id[group_id]:
            raise ValueError("bonded group return history is incomplete")
        if pending and not group_members_by_id[group_id] & returned_from_shooters:
            raise ValueError("active bonded group has unreconciled return history")

    current_return_events = {
        shooter_id: event_index
        for shooter_id, event_index in latest_return_index.items()
        if shooter_id in returned_from_shooters
    }
    if any(
        current_return_events[shooter_id]
        <= latest_reactivation_index.get(shooter_id, -1)
        for shooter_id in current_return_events
    ):
        raise ValueError("returned shooter has no return event after reactivation")

    # If a return event exists for a shooter that is currently not in storage,
    # its latest lifecycle transition must be a later group reactivation.
    # Otherwise the event history contradicts the restored shooter flags.
    for shooter_id, return_index in latest_return_index.items():
        if shooter_id not in returned_from_shooters:
            if latest_reactivation_index.get(shooter_id, -1) <= return_index:
                raise ValueError(
                    "active shooter has a return event without later reactivation"
                )
    event_order = sorted(
        current_return_events,
        key=current_return_events.get,
    )
    expected_event_order = [
        shooter_id for shooter_id in returned_ids
        if shooter_id in current_return_events
    ]
    if event_order != expected_event_order:
        raise ValueError("return event order conflicts with returned_ids")

    # Run after group-wide return-cycle checks so those established, more
    # specific diagnostics remain stable for bonded groups.
    _validate_return_point_event_history(events)
    _validate_group_entry_event_history(events, group_members_by_id)
    _validate_rotation_and_lap_history(events, config, shooter_by_id)

    if failed and events[-1].get("tick") != tick_count:
        raise ValueError("failure event tick must match the final simulator tick")
    if failed and events[-1].get("reason") != failure_reason:
        raise ValueError("failure event reason does not match simulator state")

    sim.tick_count = tick_count
    sim.failed = failed
    sim.failure_reason = failure_reason
    sim.events = copy.deepcopy(events)
    sim.returned_ids = list(returned_ids)
    return sim
