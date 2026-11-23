import unittest
from unittest.mock import patch

from decision_planner import plan_next_decision
from game_state import GameState
from powerups import PowerUpInventory


class UnifiedDecisionPlannerTests(unittest.TestCase):
    def setUp(self):
        self.state = GameState(board=[
            ["red", "blue"],
            ["red", None],
        ])

    def test_combines_ordinary_plan_and_powerup_advice(self):
        inventory = PowerUpInventory(
            gold=50, prices={"dragon_roar": 10}, charges={"dragon_roar": 1}
        )
        with patch("decision_planner.plan_next_move", return_value=("S1",)) as ordinary:
            result = plan_next_decision(
                self.state,
                planning_report={"fixture": True},
                identity_audit={"fixture": True},
                candidate_report={"fixture": True},
                snapshot_report={"fixture": True},
                powerup_inventory=inventory,
            )
        ordinary.assert_called_once()
        self.assertEqual(result["ordinary_move"], ("S1",))
        self.assertTrue(result["ordinary_move_evidence_gated"])
        self.assertTrue(any(
            item["name"] == "dragon_roar"
            for item in result["powerup_advice"]["candidates"]
        ))
        self.assertTrue(result["powerup_advice"]["strategic_ranking"]["eligible"])
        self.assertFalse(result["game_taps_enabled"])
        self.assertFalse(result["actions_performed"])

    def test_without_inventory_keeps_ordinary_planner_output(self):
        with patch("decision_planner.plan_next_move", return_value=None):
            result = plan_next_decision(self.state)
        self.assertIsNone(result["ordinary_move"])
        self.assertIsNone(result["powerup_advice"])

    def test_invalid_inventory_fails_closed(self):
        invalid = PowerUpInventory(gold=True)
        with patch("decision_planner.plan_next_move", return_value=None):
            result = plan_next_decision(
                self.state, powerup_inventory=invalid
            )
        self.assertFalse(result["powerup_advice"]["eligible"])
        self.assertFalse(result["game_taps_enabled"])


if __name__ == "__main__":
    unittest.main()
