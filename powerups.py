"""Evidence-gated model of the four in-level shop power-ups.

This module models resource accounting and hypothetical effects only. It never
touches the game or assumes prices, charges, or Extra Tray slot increments.
"""
from dataclasses import dataclass, field
from typing import Optional


POWER_UPS = {
    "extra_tray": {
        "display_name": "Extra Tray",
        "button_index": 1,
        "effect": "increase_conveyor_capacity",
    },
    "magic_glove": {
        "display_name": "Magic Glove",
        "button_index": 2,
        "effect": "select_any_board_circle_to_conveyor",
    },
    "angel_slime": {
        "display_name": "Angel Slime",
        "button_index": 3,
        "effect": "clear_pixels_matching_selected_circle_colour",
    },
    "dragon_roar": {
        "display_name": "Dragon Roar",
        "button_index": 4,
        "effect": "clear_all_pixels_of_selected_colour",
    },
}


@dataclass
class PowerUpInventory:
    """Known gold and power-up stock; unknown values remain None."""
    gold: Optional[int] = None
    prices: dict = field(default_factory=dict)
    charges: dict = field(default_factory=dict)
    extra_tray_slots: Optional[int] = None

    def validate(self):
        errors = []
        if self.gold is not None and (type(self.gold) is not int or self.gold < 0):
            errors.append("Gold must be a known non-negative integer or None")
        for name, price in self.prices.items():
            if name not in POWER_UPS:
                errors.append(f"Unknown power-up price key: {name}")
            if type(price) is not int or price < 0:
                errors.append(f"Invalid price for {name}")
        for name, count in self.charges.items():
            if name not in POWER_UPS:
                errors.append(f"Unknown power-up inventory key: {name}")
            if type(count) is not int or count < 0:
                errors.append(f"Invalid charge count for {name}")
        if self.extra_tray_slots is not None and (
            type(self.extra_tray_slots) is not int or self.extra_tray_slots < 0
        ):
            errors.append("Extra Tray slot increment must be a non-negative integer or None")
        return errors

    def record_level_gold_reward(self, amount):
        """Record an observed level reward; reject guesses and malformed values."""
        if type(amount) is not int or amount < 0:
            raise ValueError("Level gold reward must be a non-negative integer")
        if self.gold is None:
            raise ValueError("Current gold balance must be observed before adding a reward")
        self.gold += amount
        return self.gold

    def can_afford(self, name):
        if name not in POWER_UPS or self.gold is None or name not in self.prices:
            return None
        return self.gold >= self.prices[name]

    def purchase_plan(self, name):
        """Return a purchase recommendation, never debit gold or buy."""
        if name not in POWER_UPS:
            return {"eligible": False, "reason": "UNKNOWN_POWER_UP"}
        if self.validate():
            return {"eligible": False, "reason": "INVALID_RESOURCE_STATE"}
        if self.gold is None or name not in self.prices:
            return {"eligible": None, "reason": "GOLD_OR_PRICE_UNOBSERVED"}
        return {
            "eligible": self.gold >= self.prices[name],
            "reason": "AFFORDABLE" if self.gold >= self.prices[name] else "INSUFFICIENT_GOLD",
            "gold": self.gold,
            "price": self.prices[name],
            "purchase_performed": False,
        }


def describe_power_up_use(name, *, selected_colour=None, board_circle=None,
                          extra_slots=None):
    """Describe a candidate effect from observed inputs; do not apply it."""
    if name not in POWER_UPS:
        return {"eligible": False, "reason": "UNKNOWN_POWER_UP"}
    if name == "extra_tray":
        slots = extra_slots
        if type(slots) is not int or slots <= 0:
            return {"eligible": None, "reason": "SLOT_INCREMENT_UNOBSERVED"}
        return {"eligible": True, "effect": "increase_conveyor_capacity",
                "slots_added": slots, "game_action_performed": False}
    if name == "magic_glove":
        if board_circle is None:
            return {"eligible": None, "reason": "BOARD_CIRCLE_NOT_SELECTED"}
        return {"eligible": True, "effect": "select_any_board_circle_to_conveyor",
                "board_circle": board_circle, "visibility_bypass": True,
                "game_action_performed": False}
    if selected_colour is None:
        return {"eligible": None, "reason": "TARGET_COLOUR_UNOBSERVED"}
    effect = POWER_UPS[name]["effect"]
    return {"eligible": True, "effect": effect,
            "selected_colour": selected_colour,
            "game_action_performed": False}
