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


def score_powerup_candidates(state, inventory, result, *,
                             purchase_cost_weight=0.20,
                             last_charge_reserve_penalty=0.10,
                             urgency_weight=0.20):
    """Attach transparent heuristic use/purchase scores to candidate options.

    Scores are decision-support heuristics, not calibrated win probabilities.
    Use and purchase are scored separately so an owned charge is not confused
    with an affordable shop purchase. Unknown evidence never becomes a score.
    """
    if not isinstance(inventory, PowerUpInventory) or inventory.validate():
        return {"eligible": False, "reason": "INVALID_RESOURCE_STATE", "candidates": []}
    if not isinstance(result, dict) or result.get("eligible") is not True:
        return {"eligible": False, "reason": "INVALID_CANDIDATE_REPORT", "candidates": []}
    weights = (purchase_cost_weight, last_charge_reserve_penalty, urgency_weight)
    if any(isinstance(x, bool) or not isinstance(x, (int, float)) or x < 0 for x in weights):
        return {"eligible": False, "reason": "INVALID_SCORING_WEIGHTS", "candidates": []}
    remaining = getattr(state, "remaining_pixels", None)
    if type(remaining) is not int or remaining < 0:
        return {"eligible": False, "reason": "UNKNOWN_BOARD_REMAINING_COUNT", "candidates": []}

    scored = []
    for original in result.get("candidates", []):
        if not isinstance(original, dict):
            continue
        item = dict(original)
        impact = item.get("estimated_board_pixels_affected")
        if type(impact) is not int or impact < 0:
            item.update({"use_score": None, "purchase_score": None,
                         "score_status": "IMPACT_UNQUANTIFIED"})
            scored.append(item)
            continue
        impact_ratio = min(1.0, impact / remaining) if remaining else 0.0
        detail = item.get("details") or {}
        urgency = 0.0
        if item.get("name") == "extra_tray":
            free = detail.get("current_conveyor_free")
            if type(free) is int and free >= 0:
                urgency = max(0.0, min(1.0, (2 - free) / 2))
        base_value = (1.0 - urgency_weight) * impact_ratio + urgency_weight * urgency
        charges = item.get("charge_count")
        reserve_penalty = last_charge_reserve_penalty if charges == 1 else 0.0
        use_score = None
        if item.get("use_eligibility") is True:
            use_score = max(0.0, min(1.0, base_value - reserve_penalty))
        purchase_score = None
        if item.get("purchase_recommendation_eligibility") is True:
            price = inventory.prices.get(item.get("name"))
            gold = inventory.gold
            if type(price) is int and type(gold) is int and gold > 0:
                cost_ratio = min(1.0, price / gold)
                purchase_score = max(0.0, min(1.0, base_value - purchase_cost_weight * cost_ratio))
            elif price == 0 and gold == 0:
                purchase_score = base_value
        item.update({
            "observed_impact_fraction": impact_ratio,
            "conveyor_urgency": urgency,
            "use_score": use_score,
            "purchase_score": purchase_score,
            "score_status": "HEURISTIC_ONLY_NOT_GAMEPLAY_CALIBRATED",
        })
        scored.append(item)
    scored.sort(key=lambda item: max(
        item.get("use_score") if item.get("use_score") is not None else -1.0,
        item.get("purchase_score") if item.get("purchase_score") is not None else -1.0,
    ), reverse=True)
    return {
        "eligible": True,
        "ranking_basis": "transparent_heuristic_not_win_probability",
        "weights": {
            "purchase_cost": purchase_cost_weight,
            "last_charge_reserve": last_charge_reserve_penalty,
            "conveyor_urgency": urgency_weight,
        },
        "candidates": scored,
        "game_action_performed": False,
    }


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
            "purchase_recommendation_eligibility": affordability["eligible"] if use_eligibility is False else False,
            "decision_status": (
                "READY_TO_USE" if use_eligibility is True
                else "RESOURCE_STATE_UNCERTAIN" if use_eligibility is None
                else "PURCHASE_POSSIBLE" if affordability["eligible"] is True
                else "RESOURCE_STATE_UNCERTAIN"
            ),
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
