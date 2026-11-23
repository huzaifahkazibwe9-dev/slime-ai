import unittest

from powerups import (
    POWER_UPS, PowerUpInventory, describe_power_up_use,
)


class PowerUpCatalogTests(unittest.TestCase):
    def test_four_buttons_keep_left_to_right_order_and_names(self):
        self.assertEqual(
            [(name, item["display_name"], item["button_index"])
             for name, item in POWER_UPS.items()],
            [
                ("extra_tray", "Extra Tray", 1),
                ("magic_glove", "Magic Glove", 2),
                ("angel_slime", "Angel Slime", 3),
                ("dragon_roar", "Dragon Roar", 4),
            ],
        )

    def test_unknown_gold_and_prices_are_not_guessed(self):
        inventory = PowerUpInventory()
        self.assertIsNone(inventory.can_afford("extra_tray"))
        self.assertEqual(
            inventory.purchase_plan("extra_tray")["reason"],
            "GOLD_OR_PRICE_UNOBSERVED",
        )

    def test_purchase_plan_never_spends_gold(self):
        inventory = PowerUpInventory(
            gold=100, prices={"extra_tray": 40}
        )
        before = inventory.gold
        plan = inventory.purchase_plan("extra_tray")
        self.assertTrue(plan["eligible"])
        self.assertFalse(plan["purchase_performed"])
        self.assertEqual(inventory.gold, before)

    def test_insufficient_gold_is_reported(self):
        inventory = PowerUpInventory(
            gold=10, prices={"dragon_roar": 25}
        )
        self.assertFalse(inventory.purchase_plan("dragon_roar")["eligible"])

    def test_magic_glove_can_target_unseen_board_circle(self):
        result = describe_power_up_use(
            "magic_glove", board_circle={"row": 8, "column": 4,
                                         "visibility": "unseen"}
        )
        self.assertTrue(result["eligible"])
        self.assertTrue(result["visibility_bypass"])
        self.assertFalse(result["game_action_performed"])

    def test_angel_slime_requires_selected_circle_colour(self):
        self.assertIsNone(
            describe_power_up_use("angel_slime")["eligible"]
        )
        result = describe_power_up_use(
            "angel_slime", selected_colour="violet"
        )
        self.assertEqual(
            result["effect"], "clear_pixels_matching_selected_circle_colour"
        )
        self.assertFalse(result["game_action_performed"])

    def test_dragon_roar_clears_all_pixels_of_target_colour(self):
        result = describe_power_up_use(
            "dragon_roar", selected_colour="cyan"
        )
        self.assertEqual(
            result["effect"], "clear_all_pixels_of_selected_colour"
        )
        self.assertEqual(result["selected_colour"], "cyan")
        self.assertFalse(result["game_action_performed"])

    def test_extra_tray_requires_observed_slot_increment(self):
        self.assertIsNone(
            describe_power_up_use("extra_tray")["eligible"]
        )
        result = describe_power_up_use("extra_tray", extra_slots=2)
        self.assertEqual(result["slots_added"], 2)

    def test_resource_validation_rejects_boolean_counts(self):
        self.assertTrue(PowerUpInventory(gold=True).validate())
        self.assertTrue(PowerUpInventory(
            gold=10, prices={"magic_glove": True}
        ).validate())
        self.assertTrue(PowerUpInventory(
            charges={"angel_slime": False}
        ).validate())


if __name__ == "__main__":
    unittest.main()
