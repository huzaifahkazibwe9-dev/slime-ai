from dataclasses import dataclass, field
from typing import Optional
import time

CONVEYOR_LIMIT = 5
STORAGE_LIMIT = 5
LIFE_INTERVAL = 30 * 60

DIRECTIONS = {
    "up": (0, -1),
    "down": (0, 1),
    "left": (-1, 0),
    "right": (1, 0),
}


@dataclass
class Shooter:
    id: str
    color: Optional[str]
    ammo: Optional[int]
    direction: str = "up"
    x: int = 0
    y: int = 0
    group_id: Optional[str] = None
    rotation_progress: float = 0.0
    accessible: bool = False
    bonded_ids: list = field(default_factory=list)
    revealed: bool = True
    screen_center: Optional[tuple] = None
    screen_box: Optional[tuple] = None
    screen_center_verified: bool = False
    panel_center: Optional[tuple] = None
    panel_box: Optional[tuple] = None

    def valid(self):
        if self.ammo is not None and self.ammo < 0:
            return False

        if self.direction not in DIRECTIONS:
            return False

        if not 0.0 <= self.rotation_progress < 1.0:
            return False

        if self.revealed:
            if self.color is None or self.ammo is None:
                return False

        if self.id in self.bonded_ids:
            return False

        if len(self.bonded_ids) != len(set(self.bonded_ids)):
            return False

        return True


@dataclass
class LifeState:
    lives: int
    last_regeneration: float
    maximum: Optional[int] = None

    def available(self):
        if self.maximum is not None:
            return min(self.lives, self.maximum)
        return self.lives

    def update(self, now=None):
        now = time.time() if now is None else now

        if self.maximum is not None and self.lives >= self.maximum:
            return self.lives

        elapsed = max(0, now - self.last_regeneration)
        gained = int(elapsed // LIFE_INTERVAL)

        if gained:
            self.lives += gained

            if self.maximum is not None:
                self.lives = min(self.lives, self.maximum)

            self.last_regeneration += gained * LIFE_INTERVAL

        return self.lives

    def seconds_until_next(self, now=None):
        now = time.time() if now is None else now

        if self.maximum is not None and self.lives >= self.maximum:
            return 0

        elapsed = max(0, now - self.last_regeneration)
        return max(0, LIFE_INTERVAL - int(elapsed % LIFE_INTERVAL))


@dataclass
class GameState:
    board: list
    shooters: dict = field(default_factory=dict)
    conveyor: list = field(default_factory=list)
    storage: list = field(default_factory=list)
    level: Optional[int] = None
    lives: Optional[LifeState] = None

    accelerated_mode: Optional[bool] = None
    rotation_speed: Optional[float] = None
    observed_remaining_shooters: Optional[int] = None

    @property
    def height(self):
        return len(self.board)

    @property
    def width(self):
        return len(self.board[0]) if self.board else 0

    @property
    def remaining_pixels(self):
        return sum(
            pixel is not None
            for row in self.board
            for pixel in row
        )

    @property
    def conveyor_free(self):
        return CONVEYOR_LIMIT - len(self.conveyor)

    @property
    def storage_free(self):
        return STORAGE_LIMIT - len(self.storage)

    @property
    def active_circle_count(self):
        return len(self.conveyor) + len(self.storage)

    def pixel_at(self, x, y):
        if 0 <= y < self.height and 0 <= x < self.width:
            return self.board[y][x]
        return None

    def can_add_to_conveyor(self, count=1):
        return count > 0 and count <= self.conveyor_free

    def can_return_from_storage(self, shooter_id):
        return (
            shooter_id in self.storage
            and self.conveyor_free >= 1
        )

    def transfer_from_storage(self, shooter_id):
        if not self.can_return_from_storage(shooter_id):
            return False

        self.storage.remove(shooter_id)
        self.conveyor.append(shooter_id)
        self.shooters[shooter_id].rotation_progress = 0.0

        return True

    def accessible_shooters(self):
        return [
            shooter
            for shooter in self.shooters.values()
            if shooter.accessible
        ]

    def bonded_group(self, shooter_id):
        """Return the full connected bonded component, in stable order."""
        if shooter_id not in self.shooters:
            return []

        pending = [shooter_id]
        visited = set()
        ordered = []

        while pending:
            current = pending.pop(0)
            if current in visited:
                continue
            shooter = self.shooters.get(current)
            if shooter is None:
                return []
            visited.add(current)
            ordered.append(current)
            for member in shooter.bonded_ids:
                if member not in self.shooters:
                    return []
                if member not in visited and member not in pending:
                    pending.append(member)
            if len(visited) > 3:
                return []

        return sorted(ordered)

    def bonded_group_id(self, shooter_id):
        """Return one canonical ID for a complete bonded component.

        Explicit group_id values must agree across every member. If none are
        supplied, the lexicographically smallest member is the stable ID.
        """
        members = self.bonded_group(shooter_id)
        if not members:
            return None
        explicit = {
            str(self.shooters[member].group_id)
            for member in members
            if self.shooters[member].group_id is not None
        }
        if len(explicit) > 1:
            return None
        return next(iter(explicit)) if explicit else min(members)

    def can_select_group(self, shooter_id):
        group = self.bonded_group(shooter_id)

        if not group:
            return False

        if not self.shooters[shooter_id].accessible:
            return False

        if any(member in self.conveyor or member in self.storage
               for member in group):
            return False

        return self.can_add_to_conveyor(len(group))

    def select_group(self, shooter_id):
        if not self.can_select_group(shooter_id):
            return False

        group = self.bonded_group(shooter_id)

        for member in group:
            self.conveyor.append(member)
            self.shooters[member].accessible = False

        return True

    def validate(self):
        errors = []

        if not self.board:
            errors.append("Board is empty")
        elif any(len(row) != self.width for row in self.board):
            errors.append("Board rows have different widths")

        if len(self.conveyor) > CONVEYOR_LIMIT:
            errors.append("Conveyor capacity exceeded")

        if len(self.storage) > STORAGE_LIMIT:
            errors.append("Storage capacity exceeded")

        for shooter_id, shooter in self.shooters.items():
            if shooter.id != shooter_id:
                errors.append(f"Shooter ID mismatch: {shooter_id}")

            if not shooter.valid():
                errors.append(f"Invalid shooter: {shooter_id}")

            for member in shooter.bonded_ids:
                if member not in self.shooters:
                    errors.append(
                        f"Unknown bonded shooter: {member}"
                    )
                elif shooter_id not in self.shooters[member].bonded_ids:
                    errors.append(
                        f"Asymmetric bond: {shooter_id} and {member}"
                    )

        # A bonded component is one atomic selectable unit. Validate the
        # whole connected component, not just each shooter's direct links.
        checked_groups = set()
        for shooter_id in self.shooters:
            if shooter_id in checked_groups:
                continue
            group = self.bonded_group(shooter_id)
            if not group:
                # Missing references and oversized components are already
                # reported by the per-edge checks below / above.
                continue
            checked_groups.update(group)
            if len(group) > 3:
                errors.append(
                    "Bonded group exceeds maximum size of 3: "
                    + ", ".join(group)
                )
            explicit_ids = {
                str(self.shooters[member].group_id)
                for member in group
                if self.shooters[member].group_id is not None
            }
            if len(explicit_ids) > 1:
                errors.append(
                    "Inconsistent group_id values in bonded component: "
                    + ", ".join(group)
                )

        occupied = self.conveyor + self.storage

        for shooter_id in occupied:
            if shooter_id not in self.shooters:
                errors.append(f"Unknown shooter: {shooter_id}")

        if len(occupied) != len(set(occupied)):
            errors.append("A shooter occupies multiple positions")

        return errors


if __name__ == "__main__":
    state = GameState(
        board=[
            ["blue", "blue", "red"],
            ["blue", None, "red"],
            ["green", "green", "red"],
        ],
        shooters={
            "R1": Shooter(
                "R1", "red", 20, "up",
                accessible=True
            )
        },
        conveyor=["R1"],
        level=39,
    )

    print("ENHANCED GAME-STATE ENGINE")
    print("==========================")
    print("Board:", state.width, "x", state.height)
    print("Remaining pixels:", state.remaining_pixels)
    print("Conveyor spaces:", state.conveyor_free)
    print("Storage spaces:", state.storage_free)
    print("Accessible shooters:", len(state.accessible_shooters()))
    print("Validation:", state.validate())
