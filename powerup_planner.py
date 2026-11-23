"""Compare hypothetical power-up choices against ordinary board state.

All outputs are advisory. This module does not purchase, select, destroy,
modify a GameState, or issue device input. Unknown stock/prices remain unknown.
"""
from powerups import POWER_UPS, PowerUpInventory, describe_power_up_use


def _colour_counts(board):
    counts = {}
    for row in board:
        for colour in row:
            if colour is not None:
                counts[colour] = counts.get(colour, 0) + 1
    return counts


def evaluate_powerup_candidates(state, inventory, *, hidden_board_circles=None,
                                 observed_extra_slots=None):
    """Return ranked advisory candidates without changing state or inventory.

    hidden_board_circles must contain explicitly observed records with row,
    column, colour, and visibility fields. A hidden circle's colour is never
    inferred from unseen pixels.
    """
    if not isinstance(inventory, PowerUpInventory) or inventory.validate():
        return {"eligible": False, "reason": "INVALID_RESOURCE_STATE",
                "candidates": [], "game_action_performed": False}
    if not hasattr(state, "board") or not isinstance(state.board, list):
        return {"eligible": False, "reason": "INVALID_GAME_STATE",
                "candidates": [], "game_action_performed": False}

    counts = _colour_counts(state.board)
    candidates = []

    def add(name, target=None, benefit=0, detail=None):
        affordability = inventory.purchase_plan(name)
        charges = inventory.charges.get(name)
        use_eligibility = True if charges is not None and charges > 0 else (False if charges == 0 else None)
        # Owned stock remains usable even if another purchase is unaffordable.
        if use_eligibility is False and affordability["eligible"] is False:
            return
        candidates.append({
            "name": name,
            "display_name": POWER_UPS[name]["display_name"],
            "target": target,
            "estimated_board_pixels_affected": benefit,
            "purchase_eligibility": affordability["eligible"],
            "charge_count": charges,
            "use_eligibility": use_eligibility,
            "purchase_recommendation_eligibility": affordability["eligible"] if use_eligibility is not True else False,
            "decision_status": "READY_TO_USE" if use_eligibility is True else ("PURCHASE_POSSIBLE" if affordability["eligible"] is True else "RESOURCE_STATE_UNCERTAIN"),
            "estimated_value_basis": "observed_board_pixel_count_only",
            "details": detail or {},
            "game_action_performed": False,
        })

    # Extra Tray is valuable only when both the capacity increment and a
    # constrained conveyor are observed.
    free = getattr(state, "conveyor_free", None)
    if (type(observed_extra_slots) is int and observed_extra_slots > 0
            and type(free) is int and free <= 1):
        add("extra_tray", benefit=0, detail={
            "slots_added": observed_extra_slots,
            "current_conveyor_free": free,
            "reason": "LOW_CONVEYOR_HEADROOM",
        })

    for circle in hidden_board_circles or []:
        if not isinstance(circle, dict):
            continue
        if (circle.get("visibility") != "unseen"
                or type(circle.get("row")) is not int
                or type(circle.get("column")) is not int
                or not isinstance(circle.get("colour"), str)
                or not circle["colour"]):
            continue
        colour = circle["colour"]
        add("magic_glove", target={
            "row": circle["row"], "column": circle["column"],
            "colour": colour, "visibility": "unseen",
        }, benefit=counts.get(colour, 0), detail={
            "effect": "select_any_board_circle_to_conveyor",
            "colour_source": "explicit_observation",
        })

    # Angel Slime and Dragon Roar use the user's described colour-targeted
    # effects. Counts are estimates from the current board snapshot.
    for colour, count in sorted(counts.items(), key=lambda item: (-item[1], str(item[0]))):
        if count <= 0:
            continue
        angel = describe_power_up_use("angel_slime", selected_colour=colour)
        dragon = describe_power_up_use("dragon_roar", selected_colour=colour)
        if angel.get("eligible") is True:
            add("angel_slime", target=colour, benefit=count,
                detail={"effect": angel["effect"], "basis": "current_board_count"})
        if dragon.get("eligible") is True:
            add("dragon_roar", target=colour, benefit=count,
                detail={"effect": dragon["effect"], "basis": "current_board_count"})

    # Stable deterministic ordering: greater estimated board impact first;
    # known-affordable options precede unknown affordability at equal impact.
    candidates.sort(key=lambda item: (
        item["estimated_board_pixels_affected"],
        item["purchase_eligibility"] is True,
        item["name"],
    ), reverse=True)
    return {
        "eligible": True,
        "board_colour_counts": counts,
        "candidates": candidates,
        "inventory_unchanged": True,
        "state_unchanged": True,
        "game_action_performed": False,
    }
