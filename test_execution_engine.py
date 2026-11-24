import copy
import unittest

from execution_engine import run_dry_simulation, _simulate_conveyor_batch
from game_state import GameState, Shooter


class ExecutionEngineTests(unittest.TestCase):

    def make_state(self, board, shooters, conveyor=None):
        return GameState(
            board=board,
            shooters={item.id: item for item in shooters},
            conveyor=conveyor or [],
        )

    def test_matching_pixels_removed(self):
        state = self.make_state([["red", "red"]], [
            Shooter("R", "red", 3, "right", -1, 0, accessible=True)
        ])
        report = run_dry_simulation(state)
        self.assertEqual(report["best"]["pixels_removed"], 2)
        self.assertEqual(report["best"]["remaining_pixels"], 0)

    def test_source_state_unchanged(self):
        state = self.make_state([["red", "red"]], [
            Shooter("R", "red", 3, "right", -1, 0, accessible=True)
        ])
        before = copy.deepcopy(state)
        report = run_dry_simulation(state)
        self.assertTrue(report["source_state_unchanged"])
        self.assertEqual(state.board, before.board)
        self.assertEqual(state.shooters["R"].ammo, before.shooters["R"].ammo)

    def test_different_colour_blocks_shot(self):
        state = self.make_state([["blue", "red"]], [
            Shooter("R", "red", 3, "right", -1, 0, accessible=True)
        ])
        report = run_dry_simulation(state)
        self.assertEqual(report["best"]["pixels_removed"], 0)
        self.assertGreater(report["best"]["blocked_attempts"], 0)

    def test_bonded_group_selected_together(self):
        a = Shooter(
            "A", "red", 2, "right", -1, 0,
            accessible=True, group_id="pair", bonded_ids=["B"]
        )
        b = Shooter(
            "B", "blue", 2, "left", 2, 0,
            accessible=False, group_id="pair", bonded_ids=["A"]
        )
        state = self.make_state([["red", None, "blue"]], [a, b])
        report = run_dry_simulation(state)
        self.assertEqual(report["best"]["groups"], [["A", "B"]])
        self.assertEqual(report["best"]["conveyor_used"], 2)

    def test_conveyor_dry_run_uses_canonical_explicit_group_id(self):
        a = Shooter(
            "A", "red", 2, "right", -1, 0,
            accessible=True, group_id="pair-42", bonded_ids=["B"]
        )
        b = Shooter(
            "B", "blue", 2, "left", 2, 0,
            accessible=False, group_id="pair-42", bonded_ids=["A"]
        )
        original = self.make_state([["red", None, "blue"]], [a, b])
        simulated = copy.deepcopy(original)
        self.assertTrue(simulated.select_group("A"))
        report = _simulate_conveyor_batch(original, simulated, [("A", "B")])
        self.assertTrue(report["batch_selection_valid"])
        self.assertFalse(report["failed"])
        active = report["active_shooters"]
        self.assertEqual(len(active), 2)
        self.assertEqual({item["group_id"] for item in active}, {"pair-42"})

    def test_validation_reports_bonded_component_over_three(self):
        shooters = [
            Shooter("A", "red", 2, "right", -1, 0,
                    accessible=True, bonded_ids=["B"]),
            Shooter("B", "blue", 2, "left", 2, 0,
                    bonded_ids=["A", "C"]),
            Shooter("C", "green", 2, "up", 0, -1,
                    bonded_ids=["B", "D"]),
            Shooter("D", "yellow", 2, "down", 0, 2,
                    bonded_ids=["C"]),
        ]
        state = self.make_state([["red"]], shooters)
        errors = state.validate()
        self.assertTrue(any(
            "Bonded group exceeds maximum size of 3" in error
            for error in errors
        ))
        self.assertFalse(state.can_select_group("A"))

    def test_asymmetric_bond_observation_cannot_be_selected(self):
        a = Shooter(
            "A", "red", 2, "right", -1, 0,
            accessible=True, bonded_ids=["B"]
        )
        b = Shooter(
            "B", "blue", 2, "left", 2, 0,
            bonded_ids=[]
        )
        state = self.make_state([[ "red", None, "blue" ]], [a, b])
        self.assertFalse(state.can_select_group("A"))
        self.assertFalse(state.select_group("A"))
        self.assertEqual(state.conveyor, [])

    def test_conflicting_bond_group_ids_cannot_be_selected(self):
        a = Shooter(
            "A", "red", 2, "right", -1, 0,
            accessible=True, group_id="pair-a", bonded_ids=["B"]
        )
        b = Shooter(
            "B", "blue", 2, "left", 2, 0,
            group_id="pair-b", bonded_ids=["A"]
        )
        state = self.make_state([[ "red", None, "blue" ]], [a, b])
        self.assertIsNone(state.bonded_group_id("A"))
        self.assertFalse(state.can_select_group("A"))
        self.assertFalse(state.select_group("A"))
        self.assertEqual(state.conveyor, [])

    def test_malformed_bond_metadata_fails_closed_without_raising(self):
        malformed_values = [None, "B", [["B"]], [None], [1]]
        for malformed in malformed_values:
            with self.subTest(bonded_ids=malformed):
                shooter = Shooter(
                    "A", "red", 2, "right", -1, 0,
                    accessible=True, bonded_ids=malformed
                )
                state = self.make_state([["red"]], [shooter])
                self.assertFalse(shooter.valid())
                self.assertEqual(state.bonded_group("A"), [])
                self.assertFalse(state.can_select_group("A"))
                validation_errors = state.validate()
                self.assertTrue(any(
                    ("Invalid bonded_ids" in error
                     or "Invalid bonded shooter reference" in error)
                    for error in validation_errors
                ))
                self.assertEqual(state.conveyor, [])

    def test_non_string_group_id_fails_closed(self):
        a = Shooter(
            "A", "red", 2, "right", -1, 0,
            accessible=True, group_id=["not", "a", "string"]
        )
        state = self.make_state([["red"]], [a])
        self.assertFalse(a.valid())
        self.assertFalse(state.can_select_group("A"))
        self.assertTrue(any(
            "Invalid shooter: A" in error for error in state.validate()
        ))

    def test_existing_conveyor_partial_bonded_group_is_rejected(self):
        a = Shooter(
            "A", "red", 2, "right", -1, 0,
            group_id="pair", bonded_ids=["B"]
        )
        b = Shooter(
            "B", "blue", 2, "left", 2, 0,
            group_id="pair", bonded_ids=["A"]
        )
        original = self.make_state(
            [["red", None, "blue"]], [a, b], conveyor=["A"]
        )
        simulated = copy.deepcopy(original)
        report = _simulate_conveyor_batch(original, simulated, [])
        self.assertFalse(report["batch_selection_valid"])
        self.assertEqual(
            report["failure_reason"], "PARTIAL_BONDED_GROUP_ON_CONVEYOR"
        )

    def test_unknown_ammo_on_existing_conveyor_is_rejected(self):
        hidden = Shooter(
            "H", None, None, "right", -1, 0, revealed=False
        )
        original = self.make_state([[None]], [hidden], conveyor=["H"])
        simulated = copy.deepcopy(original)
        report = _simulate_conveyor_batch(original, simulated, [])
        self.assertFalse(report["batch_selection_valid"])
        self.assertEqual(
            report["failure_reason"], "UNKNOWN_AMMO_ON_EXISTING_CONVEYOR"
        )

    def test_three_bond_group_rejected_with_one_slot(self):
        shooters = [
            Shooter("A", "red", 1, "right", -1, 0,
                    accessible=True, bonded_ids=["B", "C"]),
            Shooter("B", "red", 1, "right", -1, 0,
                    bonded_ids=["A", "C"]),
            Shooter("C", "red", 1, "right", -1, 0,
                    bonded_ids=["A", "B"]),
        ]
        fillers = [
            Shooter(key, "blue", 1, "left", 1, 0)
            for key in ("D", "E", "F", "G")
        ]
        state = self.make_state(
            [["red"]], shooters + fillers,
            conveyor=["D", "E", "F", "G"]
        )
        report = run_dry_simulation(state)
        self.assertEqual(report["status"], "NO_LEGAL_BATCH")

    def test_live_execution_is_always_disabled(self):
        state = self.make_state([["red"]], [
            Shooter("R", "red", 1, "right", -1, 0, accessible=True)
        ])
        report = run_dry_simulation(state)
        self.assertFalse(report["live_execution_allowed"])
        self.assertFalse(report["gameplay_actions_performed"])

    def test_candidate_limit(self):
        shooters = [
            Shooter(str(i), "red", 1, "right", -1, 0, accessible=True)
            for i in range(4)
        ]
        state = self.make_state([["red"]], shooters)
        report = run_dry_simulation(state, max_candidates=3)
        self.assertLessEqual(report["candidates_examined"], 3)
        self.assertTrue(report["search_truncated"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
