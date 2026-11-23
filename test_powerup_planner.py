import unittest
from copy import deepcopy

from game_state import GameState
from powerups import PowerUpInventory
from powerup_planner import evaluate_powerup_candidates


class PowerUpPlannerTests(unittest.TestCase):
    def setUp(self):
        self.state = GameState(board=[
            ["red", "red", "blue"],
            ["red", None, "green"],
            ["blue", "blue", "blue"],
        ])
        self.inventory = PowerUpInventory(
            gold=100,
            prices={name: 10 for name in (
                "extra_tray", "magic_glove", "angel_slime", "dragon_roar"
            )},
            charges={name: 1 for name in (
                "extra_tray", "magic_glove", "angel_slime", "dragon_roar"
            )},
        )

    def test_colour_powerups_rank_by_observed_board_impact(self):
        result = evaluate_powerup_candidates(self.state, self.inventory)
        dragon = [x for x in result["candidates"] if x["name"] == "dragon_roar"]
        self.assertEqual(dragon[0]["target"], "blue")
        self.assertEqual(dragon[0]["estimated_board_pixels_affected"], 4)

    def test_magic_glove_accepts_only_explicit_unseen_circle_observation(self):
        result = evaluate_powerup_candidates(
            self.state, self.inventory,
            hidden_board_circles=[
                {"row": 7, "column": 2, "colour": "red", "visibility": "unseen"},
                {"row": 1, "column": 1, "colour": "green", "visibility": "visible"},
                {"row": 2, "column": 1, "visibility": "unseen"},
            ],
        )
        glove = [x for x in result["candidates"] if x["name"] == "magic_glove"]
        self.assertEqual(len(glove), 1)
        self.assertEqual(glove[0]["target"]["row"], 7)

    def test_extra_tray_requires_observed_increment_and_low_headroom(self):
        result = evaluate_powerup_candidates(
            self.state, self.inventory, observed_extra_slots=2
        )
        self.assertFalse(any(x["name"] == "extra_tray" for x in result["candidates"]))

    def test_planner_does_not_mutate_state_or_inventory(self):
        state_before = deepcopy(self.state)
        inventory_before = deepcopy(self.inventory)
        evaluate_powerup_candidates(
            self.state, self.inventory,
            hidden_board_circles=[
                {"row": 4, "column": 3, "colour": "blue", "visibility": "unseen"}
            ],
            observed_extra_slots=2,
        )
        self.assertEqual(self.state, state_before)
        self.assertEqual(self.inventory, inventory_before)

    def test_unknown_prices_keep_candidates_but_mark_affordability_unknown(self):
        inventory = PowerUpInventory(charges={"dragon_roar": 1})
        result = evaluate_powerup_candidates(self.state, inventory)
        dragon = [x for x in result["candidates"] if x["name"] == "dragon_roar"]
        self.assertTrue(dragon)
        self.assertIsNone(dragon[0]["purchase_eligibility"])

    def test_zero_charges_with_affordable_price_is_purchase_only(self):
        inventory = PowerUpInventory(gold=100, prices={"dragon_roar": 1}, charges={"dragon_roar": 0})
        result = evaluate_powerup_candidates(self.state, inventory)
        dragon = [x for x in result["candidates"] if x["name"] == "dragon_roar"]
        self.assertTrue(dragon)
        self.assertFalse(dragon[0]["use_eligibility"])
        self.assertTrue(dragon[0]["purchase_recommendation_eligibility"])
        self.assertEqual(dragon[0]["decision_status"], "PURCHASE_POSSIBLE")

    def test_owned_charge_remains_usable_when_new_purchase_is_unaffordable(self):
        inventory = PowerUpInventory(gold=0, prices={"dragon_roar": 50}, charges={"dragon_roar": 1})
        result = evaluate_powerup_candidates(self.state, inventory)
        dragon = [x for x in result["candidates"] if x["name"] == "dragon_roar"]
        self.assertTrue(dragon)
        self.assertTrue(dragon[0]["use_eligibility"])
        self.assertFalse(dragon[0]["purchase_eligibility"])
        self.assertEqual(dragon[0]["decision_status"], "READY_TO_USE")

    def test_unknown_charge_is_not_marked_ready_to_use(self):
        inventory = PowerUpInventory(gold=100, prices={"dragon_roar": 1})
        result = evaluate_powerup_candidates(self.state, inventory)
        dragon = [x for x in result["candidates"] if x["name"] == "dragon_roar"]
        self.assertTrue(dragon)
        self.assertIsNone(dragon[0]["use_eligibility"])
        self.assertEqual(dragon[0]["decision_status"], "RESOURCE_STATE_UNCERTAIN")


if __name__ == "__main__":
    unittest.main()
