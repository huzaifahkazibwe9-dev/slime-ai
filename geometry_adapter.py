"""Connect verified conveyor positions to solver virtual coordinates."""

from pathlib import Path
import json

from conveyor_geometry import calculate_firing_geometry

CALIBRATION_FILE = Path("data/conveyor_calibration.json")


def apply_geometry(
    shooter,
    screen_center,
    segment,
    image_size,
    position_verified=False,
):
    if position_verified is not True:
        raise ValueError("Conveyor position must be explicitly verified")

    result = calculate_firing_geometry(
        screen_center=screen_center,
        segment=segment,
        image_size=image_size,
        position_verified=True,
    )

    shooter.x, shooter.y = result["origin"]
    shooter.direction = result["direction"]
    shooter.screen_center = tuple(screen_center)
    shooter.screen_center_verified = True

    # Geometry alone never grants gameplay access.
    shooter.accessible = False

    return result


def run_tests():
    from game_state import Shooter

    data = json.loads(CALIBRATION_FILE.read_text())
    image_size = tuple(data["image_size"])

    assert data.get("verified_by_user") is True

    print("SLIME AI — SOLVER GEOMETRY ADAPTER")
    print("=" * 42)

    for item in data["shooters"]:
        shooter = Shooter(
            id=item["id"],
            color="test",
            ammo=10,
        )

        try:
            result = apply_geometry(
                shooter,
                item["center"],
                item["segment"],
                image_size,
                position_verified=True,
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(
                f"Calibration entry {item.get('id', '<unknown>')} "
                f"({item.get('segment', '<unknown>')}) is invalid: {exc}"
            ) from exc

        assert shooter.direction == data["directions"][item["segment"]]
        assert (shooter.x, shooter.y) == result["origin"]
        assert shooter.screen_center_verified is True
        assert shooter.accessible is False

        print(
            f"[PASS] {shooter.id}: "
            f"{shooter.direction}, "
            f"origin=({shooter.x}, {shooter.y}), "
            f"first={result['first_board_cell']}"
        )

    print("\n8/8 adapter tests passed.")
    print("Shooter access remains disabled.")
    print("No game actions performed.")


if __name__ == "__main__":
    run_tests()
