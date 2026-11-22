"""Conservative, event-driven conveyor/storage simulator.

This models known capacity and rotation rules. It does not claim that
its configurable timing is an exact measurement of the live game.
Live gameplay actions are never performed here.
"""
from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class Shooter:
    shooter_id: str
    group_id: str
    ammo: int
    position: int = 0
    completed_laps: int = 0
    selected: bool = False
    returned: bool = False

    def __post_init__(self):
        if not self.shooter_id or not self.group_id:
            raise ValueError("Shooter and group IDs must be non-empty")
        if self.ammo < 0:
            raise ValueError("Ammo cannot be negative")


@dataclass
class SimulatorConfig:
    conveyor_capacity: int = 5
    storage_capacity: int = 5
    ticks_per_lap: int = 5

    def __post_init__(self):
        if min(self.conveyor_capacity, self.storage_capacity,
               self.ticks_per_lap) < 1:
            raise ValueError("Capacities and ticks_per_lap must be positive")


@dataclass
class ConveyorSimulator:
    shooters: List[Shooter]
    storage_occupied: int = 0
    config: SimulatorConfig = field(default_factory=SimulatorConfig)
    tick_count: int = 0
    failed: bool = False
    failure_reason: str = ""
    events: List[dict] = field(default_factory=list)
    returned_ids: List[str] = field(default_factory=list)

    def __post_init__(self):
        ids = [s.shooter_id for s in self.shooters]
        if len(ids) != len(set(ids)):
            raise ValueError("Shooter IDs must be unique")
        if not 0 <= self.storage_occupied <= self.config.storage_capacity:
            raise ValueError("Initial storage occupancy is out of range")
        self._by_id = {s.shooter_id: s for s in self.shooters}

    @property
    def active(self):
        return [s for s in self.shooters if s.selected and not s.returned]

    @property
    def conveyor_free(self):
        return self.config.conveyor_capacity - len(self.active)

    @property
    def storage_free(self):
        return self.config.storage_capacity - self.storage_occupied

    def _event(self, event_type, **details):
        item = {"tick": self.tick_count, "event": event_type, **details}
        self.events.append(item)
        return item

    def _fail(self, reason):
        self.failed = True
        self.failure_reason = reason
        self._event("LEVEL_FAILURE", reason=reason)
        return False

    def select_group(self, group_id):
        """Select every member of a bonded group atomically."""
        if self.failed:
            return False

        members = [
            s for s in self.shooters
            if s.group_id == group_id and not s.selected and not s.returned
        ]
        if not members:
            self._event("SELECTION_REJECTED", group_id=group_id,
                        reason="NO_AVAILABLE_GROUP_MEMBERS")
            return False

        if len(members) > self.conveyor_free:
            self._event("SELECTION_REJECTED", group_id=group_id,
                        group_size=len(members),
                        free_slots=self.conveyor_free,
                        reason="INSUFFICIENT_CONVEYOR_SPACE")
            return False

        for shooter in members:
            shooter.selected = True
            shooter.position = 0
            self._event("SHOOTER_ENTERED", shooter_id=shooter.shooter_id,
                        group_id=group_id, position=0)

        return True

    def record_shots(self, shooter_id, shots):
        """Record externally observed/simulated shots; never fires a tap."""
        if self.failed or shots < 0:
            return False
        shooter = self._by_id.get(shooter_id)
        if shooter is None or not shooter.selected or shooter.returned:
            return False
        if shots > shooter.ammo:
            self._event("SHOT_RECORD_REJECTED", shooter_id=shooter_id,
                        requested=shots, ammo=shooter.ammo)
            return False

        shooter.ammo -= shots
        self._event("AMMO_UPDATED", shooter_id=shooter_id,
                    shots_recorded=shots, ammo_remaining=shooter.ammo)
        if shooter.ammo == 0:
            self._event("SHOOTER_COMPLETED", shooter_id=shooter_id)
        return True

    def tick(self, count=1):
        """Advance the abstract conveyor by a number of rotation steps."""
        if count < 0:
            raise ValueError("Tick count cannot be negative")
        if self.failed:
            return False

        for _ in range(count):
            self.tick_count += 1

            # Snapshot prevents list mutation while processing returns.
            for shooter in list(self.active):
                shooter.position = (
                    shooter.position + 1
                ) % self.config.ticks_per_lap

                self._event("SHOOTER_ROTATED",
                            shooter_id=shooter.shooter_id,
                            position=shooter.position)

                # Reaching position zero represents one complete lap.
                if shooter.position == 0:
                    if shooter.ammo == 0:
                        if self.storage_free <= 0:
                            return self._fail(
                                "COMPLETED_SHOOTER_REACHED_RETURN_POINT "
                                "BUT_STORAGE_IS_FULL"
                            )
                        shooter.returned = True
                        self.storage_occupied += 1
                        self.returned_ids.append(shooter.shooter_id)
                        self._event(
                            "SHOOTER_RETURNED_TO_STORAGE",
                            shooter_id=shooter.shooter_id,
                            storage_occupied=self.storage_occupied,
                            storage_free=self.storage_free,
                        )
                    else:
                        shooter.completed_laps += 1
                        self._event(
                            "SHOOTER_CONTINUES_ROTATING",
                            shooter_id=shooter.shooter_id,
                            laps=shooter.completed_laps,
                            ammo_remaining=shooter.ammo,
                        )
        return not self.failed

    def reactivate_group(self, group_id):
        """Reactivate a fully returned group from storage, simulation only."""
        if self.failed:
            return False

        members = [
            s for s in self.shooters
            if s.group_id == group_id
        ]
        if not members or not all(s.returned for s in members):
            self._event(
                "STORAGE_REACTIVATION_REJECTED",
                group_id=group_id,
                reason="GROUP_NOT_FULLY_RETURNED",
            )
            return False

        count = len(members)
        if self.storage_occupied < count:
            self._event(
                "STORAGE_REACTIVATION_REJECTED",
                group_id=group_id,
                reason="INSUFFICIENT_STORAGE_OCCUPANCY",
            )
            return False

        if count > self.conveyor_free:
            self._event(
                "STORAGE_REACTIVATION_REJECTED",
                group_id=group_id,
                reason="INSUFFICIENT_CONVEYOR_SPACE",
            )
            return False

        # Validate the entire group before changing any member.
        self.storage_occupied -= count
        for shooter in members:
            shooter.returned = False
            shooter.selected = False
            shooter.position = 0
            shooter.completed_laps = 0
            if shooter.shooter_id in self.returned_ids:
                self.returned_ids.remove(shooter.shooter_id)

        self._event(
            "GROUP_REACTIVATED_FROM_STORAGE",
            group_id=group_id,
            members=[s.shooter_id for s in members],
            storage_occupied=self.storage_occupied,
        )
        return True

    def report(self):
        return {
            "simulation_only": True,
            "live_actions_performed": False,
            "live_taps_enabled": False,
            "timing_calibrated_to_game": False,
            "tick_count": self.tick_count,
            "ticks_per_lap": self.config.ticks_per_lap,
            "failed": self.failed,
            "failure_reason": self.failure_reason,
            "conveyor_capacity": self.config.conveyor_capacity,
            "conveyor_occupied": len(self.active),
            "conveyor_free": self.conveyor_free,
            "storage_capacity": self.config.storage_capacity,
            "storage_occupied": self.storage_occupied,
            "storage_free": self.storage_free,
            "active_shooters": [
                {
                    "id": s.shooter_id,
                    "group_id": s.group_id,
                    "ammo": s.ammo,
                    "position": s.position,
                    "completed_laps": s.completed_laps,
                }
                for s in self.active
            ],
            "returned_shooters": list(self.returned_ids),
            "events": list(self.events),
        }


def create_simulator(shooter_records, storage_occupied=0, config=None):
    """Build from records; optionally restore already-active conveyor state."""
    shooters = []
    for item in shooter_records:
        shooters.append(
            Shooter(
                shooter_id=str(item["id"]),
                group_id=str(item.get("group_id", item["id"])),
                ammo=int(item["ammo"]),
                position=int(item.get("position", 0)),
                completed_laps=int(item.get("completed_laps", 0)),
                selected=bool(item.get("selected", False)),
                returned=bool(item.get("returned", False)),
            )
        )
    return ConveyorSimulator(
        shooters=shooters,
        storage_occupied=storage_occupied,
        config=config or SimulatorConfig(),
    )
