from dataclasses import dataclass
from game_state import GameState, DIRECTIONS


@dataclass
class ShotResult:
    fired: bool
    removed: bool
    position: tuple = None
    reason: str = ""


def simulate_shot(state, shooter_id):
    if not isinstance(state, GameState):
        return ShotResult(False, False, reason="Invalid game state")
    if not isinstance(getattr(state, "shooters", None), dict):
        return ShotResult(False, False, reason="Invalid shooter mapping")

    shooter = state.shooters.get(shooter_id)
    if shooter is None:
        return ShotResult(False, False, reason="Unknown shooter")

    ammo = getattr(shooter, "ammo", None)
    if ammo is None:
        return ShotResult(False, False, reason="Ammunition is unknown")
    if type(ammo) is not int:
        return ShotResult(False, False, reason="Invalid ammunition")
    if ammo < 0:
        return ShotResult(False, False, reason="Invalid ammunition")
    if ammo == 0:
        return ShotResult(False, False, reason="No ammunition")

    direction = getattr(shooter, "direction", None)
    if not isinstance(direction, str) or direction not in DIRECTIONS:
        return ShotResult(False, False, reason="Invalid direction")

    shooter_x = getattr(shooter, "x", None)
    shooter_y = getattr(shooter, "y", None)
    if (
        type(shooter_x) is not int
        or type(shooter_y) is not int
    ):
        return ShotResult(False, False, reason="Invalid shooter coordinates")

    shooter_color = getattr(shooter, "color", None)
    if not isinstance(shooter_color, str) or not shooter_color:
        return ShotResult(False, False, reason="Shooter colour is unknown")

    board = getattr(state, "board", None)
    if (
        not isinstance(board, list)
        or not board
        or any(not isinstance(row, list) for row in board)
        or not board[0]
        or any(len(row) != len(board[0]) for row in board)
        or any(
            cell is not None and (not isinstance(cell, str) or not cell)
            for row in board
            for cell in row
        )
    ):
        return ShotResult(False, False, reason="Invalid board structure")

    dx, dy = DIRECTIONS[direction]

    x = shooter_x + dx
    y = shooter_y + dy

    # Check pixels in the shooter's facing direction.
    # Empty cells allow the shot to pass through.
    while 0 <= x < state.width and 0 <= y < state.height:

        pixel = state.pixel_at(x, y)

        if pixel is not None:
            # The first occupied pixel blocks everything behind it.
            if pixel == shooter_color:
                state.board[y][x] = None
                shooter.ammo -= 1

                return ShotResult(
                    True, True, (x, y), "Matching pixel removed"
                )

            return ShotResult(
                False, False, (x, y), "Blocked by another colour"
            )

        x += dx
        y += dy

    return ShotResult(False, False, reason="No reachable pixel")


def test_simulator():
    # Test 1: A matching pixel is reached through an empty cell.
    state = GameState(
        board=[
            [None, "red", None],
            [None, None, None],
            [None, None, None],
        ],
        shooters={}
    )

    from game_state import Shooter

    state.shooters["R1"] = Shooter(
        "R1", "red", 5, "right", -1, 0
    )

    result = simulate_shot(state, "R1")

    assert result.removed
    assert result.position == (1, 0)
    assert state.shooters["R1"].ammo == 4

    print("Test 1 passed: matching pixel removed.")

    # Test 2: A different colour blocks the shot.
    state = GameState(
        board=[
            ["blue", "red", None],
        ],
        shooters={
            "R1": Shooter("R1", "red", 5, "right", -1, 0)
        }
    )

    result = simulate_shot(state, "R1")

    assert not result.removed
    assert state.board[0][1] == "red"
    assert state.shooters["R1"].ammo == 5

    print("Test 2 passed: blocking works.")

    # Test 3: A second shot can reach a newly exposed pixel.
    state = GameState(
        board=[
            ["red", "red"],
        ],
        shooters={
            "R1": Shooter("R1", "red", 5, "right", -1, 0)
        }
    )

    first = simulate_shot(state, "R1")
    second = simulate_shot(state, "R1")

    assert first.removed and second.removed
    assert state.board == [[None, None]]
    assert state.shooters["R1"].ammo == 3

    print("Test 3 passed: successive shots work.")
    print("All simulator tests passed.")


if __name__ == "__main__":
    test_simulator()
