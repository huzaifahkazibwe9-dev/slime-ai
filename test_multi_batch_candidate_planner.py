import unittest
from types import SimpleNamespace
from unittest.mock import patch

from game_state import GameState
from conveyor_simulator import SimulatorConfig
import multi_batch_candidate_planner as planner


class Build11AFTests(unittest.TestCase):

    def test_batch_packing_preserves_bonded_groups(self):
        groups = [
            {"id": "pair", "members": ("A", "B"), "size": 2},
            {"id": "single", "members": ("C",), "size": 1},
            {"id": "triple", "members": ("D", "E", "F"), "size": 3},
        ]
        batches = planner._pack_batches(
            groups, 5, SimulatorConfig()
        )
        self.assertEqual(
            batches,
            [
                {"groups": ["pair", "single"], "reactivate_groups": []},
                {"groups": ["triple"], "reactivate_groups": []},
            ],
        )

    def test_initial_conveyor_space_is_respected(self):
        groups = [
            {"id": "pair", "members": ("A", "B"), "size": 2},
        ]
        self.assertIsNone(
            planner._pack_batches(
                groups, 1, SimulatorConfig()
            )
        )

    def test_oversized_group_is_rejected(self):
        groups = [
            {
                "id": "six",
                "members": tuple("ABCDEF"),
                "size": 6,
            },
        ]
        self.assertIsNone(
            planner._pack_batches(
                groups, 5, SimulatorConfig()
            )
        )

    def test_planner_ranks_simulated_candidates(self):
        state = GameState([[None]])
        state.shooters = {
            "A": SimpleNamespace(group_id="A", accessible=True),
            "B": SimpleNamespace(group_id="B", accessible=True),
        }

        def fake_simulation(private_state, batches, **kwargs):
            order = [
                group
                for batch in batches
                for group in batch["groups"]
            ]
            removed = 3 if order[0] == "A" else 1
            return {
                "schedule_valid": True,
                "simulated_pixels_removed": removed,
                "simulated_remaining_pixels": 10 - removed,
                "group_simulations": [],
                "prepared_batches": batches,
                "live_execution_allowed": False,
                "gameplay_actions_performed": False,
            }

        with (
            patch.object(GameState, "validate", return_value=[]),
            patch.object(
                planner,
                "available_groups",
                return_value=[("A",), ("B",)],
            ),
            patch.object(
                planner,
                "simulate_dynamic_multi_batch",
                side_effect=fake_simulation,
            ),
        ):
            result = planner.plan_multi_batch_candidates(state)

        self.assertEqual(result["candidate_count"], 2)
        self.assertEqual(result["best"]["candidate_order"][0], "A")
        self.assertTrue(result["source_state_unchanged"])
        self.assertFalse(result["game_taps_enabled"])

    def test_candidate_limit_is_enforced(self):
        state = GameState([[None]])
        state.shooters = {
            "A": SimpleNamespace(group_id="A", accessible=True),
            "B": SimpleNamespace(group_id="B", accessible=True),
        }

        with (
            patch.object(GameState, "validate", return_value=[]),
            patch.object(
                planner,
                "available_groups",
                return_value=[("A",), ("B",)],
            ),
            patch.object(
                planner,
                "simulate_dynamic_multi_batch",
                return_value={
                    "schedule_valid": True,
                    "simulated_pixels_removed": 1,
                    "simulated_remaining_pixels": 0,
                    "group_simulations": [],
                    "prepared_batches": [],
                },
            ),
        ):
            result = planner.plan_multi_batch_candidates(
                state, max_candidates=1
            )

        self.assertEqual(result["candidate_count"], 1)
        self.assertTrue(result["search_truncated"])
        self.assertFalse(result["completion"]["simulation_complete"])
        self.assertIn("SEARCH_TRUNCATED", result["completion"]["blockers"])

    def test_valid_partial_plan_is_not_reported_as_full_level_complete(self):
        from game_state import Shooter

        state = GameState([[None]], shooters={
            "A": Shooter("A", "red", 1, group_id="A", accessible=True),
            "B": Shooter("B", "blue", 1, group_id="B", accessible=False),
        })

        def fake_simulation(private_state, batches, **kwargs):
            return {
                "schedule_valid": True,
                "simulated_pixels_removed": 1,
                "simulated_remaining_pixels": 0,
                "group_simulations": [],
                "prepared_batches": batches,
            }

        with (
            patch.object(planner, "available_groups", return_value=[("A",)]),
            patch.object(planner, "simulate_dynamic_multi_batch", side_effect=fake_simulation),
        ):
            result = planner.plan_multi_batch_candidates(state)

        self.assertEqual(result["status"], "SIMULATED")
        self.assertFalse(result["completion"]["full_level_complete"])
        self.assertEqual(result["completion"]["unplanned_group_ids"], ["B"])
        self.assertIn("KNOWN_GROUPS_NOT_PLANNED", result["completion"]["blockers"])

    def test_complete_plan_requires_cleared_board_and_all_known_groups(self):
        from game_state import Shooter

        state = GameState([[None]], shooters={
            "A": Shooter("A", "red", 1, group_id="A", accessible=True),
        })

        def fake_simulation(private_state, batches, **kwargs):
            return {
                "schedule_valid": True,
                "simulated_pixels_removed": 1,
                "simulated_remaining_pixels": 0,
                "group_simulations": [],
                "prepared_batches": batches,
            }

        with (
            patch.object(planner, "available_groups", return_value=[("A",)]),
            patch.object(planner, "simulate_dynamic_multi_batch", side_effect=fake_simulation),
        ):
            result = planner.plan_multi_batch_candidates(state)

        self.assertTrue(result["completion"]["simulation_complete"])
        self.assertFalse(result["completion"]["full_level_complete"])
        self.assertFalse(result["completion"]["live_level_completion_verified"])
        self.assertIn(
            "CONVEYOR_TIMING_UNCALIBRATED",
            result["completion"]["blockers"],
        )
    def test_live_execution_is_never_enabled(self):
        state = GameState([[None]])

        with patch.object(GameState, "validate", return_value=[]):
            result = planner.plan_multi_batch_candidates(state)

        self.assertFalse(result["live_execution_allowed"])
        self.assertFalse(result["gameplay_actions_performed"])
        self.assertFalse(result["game_taps_enabled"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
