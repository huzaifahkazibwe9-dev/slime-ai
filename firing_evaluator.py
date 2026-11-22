"""Read-only firing path evaluation. Never performs game actions."""

from game_state import DIRECTIONS


def trace_firing_path(state, entry_cell, direction):
    """Find the first occupied board cell along a firing line."""
    if direction not in DIRECTIONS:
        raise ValueError(f"Unsupported direction: {direction}")

    x, y = entry_cell
    dx, dy = DIRECTIONS[direction]

    path_length = 0

    while 0 <= x < state.width and 0 <= y < state.height:
        path_length += 1
        colour = state.pixel_at(x, y)

        if colour is not None:
            return {
                "found": True,
                "cell": (x, y),
                "colour": colour,
                "distance": path_length - 1,
                "direction": direction,
            }

        x += dx
        y += dy

    return {
        "found": False,
        "cell": None,
        "colour": None,
        "distance": None,
        "direction": direction,
    }


def evaluate_firing_target(
    state,
    entry_cell,
    direction,
    shooter_colour=None,
):
    """Evaluate the first target without changing the game state."""
    target = trace_firing_path(state, entry_cell, direction)

    if not target["found"]:
        target["colour_match"] = None
        target["status"] = "NO_TARGET"
        return target

    if shooter_colour is None:
        target["colour_match"] = None
        target["status"] = "TARGET_FOUND_COLOUR_UNVERIFIED"
    else:
        matches = (
            target["colour"].strip().lower()
            == shooter_colour.strip().lower()
        )
        target["colour_match"] = matches
        target["status"] = (
            "MATCH" if matches else "BLOCKED_BY_DIFFERENT_COLOUR"
        )

    return target
