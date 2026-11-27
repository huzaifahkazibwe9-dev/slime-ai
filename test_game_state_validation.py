import math
import unittest

from game_state import GameState, Shooter, LifeState, CONVEYOR_LIMIT, STORAGE_LIMIT


class ShooterValidationTests(unittest.TestCase):
    def test_valid_shooter_passes(self):
        s = Shooter("S1", "red", 5, direction="up", accessible=True)
        self.assertTrue(s.valid())

    def test_boolean_ammo_rejected(self):
        s = Shooter("S1", "red", True)
        self.assertFalse(s.valid())

    def test_negative_ammo_rejected(self):
        s = Shooter("S1", "red", -1)
        self.assertFalse(s.valid())

    def test_float_ammo_rejected(self):
        s = Shooter("S1", "red", 1.5)
        self.assertFalse(s.valid())

    def test_invalid_direction_rejected(self):
        s = Shooter("S1", "red", 1, direction="diagonal")
        self.assertFalse(s.valid())

    def test_rotation_progress_out_of_range_rejected(self):
        s = Shooter("S1", "red", 1, rotation_progress=1.0)
        self.assertFalse(s.valid())
        s.rotation_progress = -0.1
        self.assertFalse(s.valid())

    def test_non_finite_rotation_progress_rejected(self):
        s = Shooter("S1", "red", 1, rotation_progress=float("nan"))
        self.assertFalse(s.valid())
        s.rotation_progress = float("inf")
        self.assertFalse(s.valid())

    def test_boolean_rotation_progress_rejected(self):
        s = Shooter("S1", "red", 1, rotation_progress=True)
        self.assertFalse(s.valid())

    def test_self_bond_rejected(self):
        s = Shooter("S1", "red", 1, bonded_ids=["S1"])
        self.assertFalse(s.valid())

    def test_duplicate_bonded_ids_rejected(self):
        s = Shooter("S1", "red", 1, bonded_ids=["S2", "S2"])
        self.assertFalse(s.valid())

    def test_unrevealed_may_omit_color_and_ammo(self):
        s = Shooter("S1", None, None, revealed=False)
        self.assertTrue(s.valid())

    def test_revealed_requires_color_and_ammo(self):
        s = Shooter("S1", None, 1, revealed=True)
        self.assertFalse(s.valid())
        s = Shooter("S1", "red", None, revealed=True)
        self.assertFalse(s.valid())


class GameStateValidationTests(unittest.TestCase):
    def _simple_board(self):
        return [["red", "blue"], ["green", None]]

    def test_empty_board_reported(self):
        state = GameState(board=[], shooters={})
        errors = state.validate()
        self.assertTrue(any("Board is empty" in e for e in errors))

    def test_non_rectangular_board_reported(self):
        state = GameState(board=[["red"], ["blue", "green"]], shooters={})
        errors = state.validate()
        self.assertTrue(any("different widths" in e for e in errors))

    def test_conveyor_capacity_exceeded_reported(self):
        state = GameState(
            board=self._simple_board(),
            conveyor=["A"] * (CONVEYOR_LIMIT + 1),
            shooters={},
        )
        errors = state.validate()
        self.assertTrue(any("Conveyor capacity exceeded" in e for e in errors))

    def test_storage_capacity_exceeded_reported(self):
        state = GameState(
            board=self._simple_board(),
            storage=["A"] * (STORAGE_LIMIT + 1),
            shooters={},
        )
        errors = state.validate()
        self.assertTrue(any("Storage capacity exceeded" in e for e in errors))

    def test_shooter_id_mismatch_reported(self):
        s = Shooter("WRONG", "red", 1)
        state = GameState(
            board=self._simple_board(),
            shooters={"RIGHT": s},
        )
        errors = state.validate()
        self.assertTrue(any("Shooter ID mismatch" in e for e in errors))

    def test_invalid_shooter_reported(self):
        s = Shooter("S1", "red", True)  # boolean ammo
        state = GameState(
            board=self._simple_board(),
            shooters={"S1": s},
        )
        errors = state.validate()
        self.assertTrue(any("Invalid shooter: S1" in e for e in errors))

    def test_unknown_occupied_shooter_reported(self):
        state = GameState(
            board=self._simple_board(),
            conveyor=["MISSING"],
            shooters={},
        )
        errors = state.validate()
        self.assertTrue(any("Unknown shooter: MISSING" in e for e in errors))

    def test_duplicate_occupation_reported(self):
        state = GameState(
            board=self._simple_board(),
            conveyor=["A"],
            storage=["A"],
            shooters={"A": Shooter("A", "red", 1)},
        )
        errors = state.validate()
        self.assertTrue(any("occupies multiple positions" in e for e in errors))

    def test_valid_minimal_state_has_no_errors(self):
        s = Shooter("S1", "red", 3, accessible=True)
        state = GameState(
            board=self._simple_board(),
            shooters={"S1": s},
        )
        self.assertEqual(state.validate(), [])

    def test_can_add_to_conveyor_respects_limit_and_positive_count(self):
        state = GameState(
            board=self._simple_board(),
            conveyor=["A"] * (CONVEYOR_LIMIT - 1),
            shooters={},
        )
        self.assertTrue(state.can_add_to_conveyor(1))
        self.assertFalse(state.can_add_to_conveyor(2))
        self.assertFalse(state.can_add_to_conveyor(0))
        self.assertFalse(state.can_add_to_conveyor(-1))

    def test_life_state_available_respects_maximum(self):
        life = LifeState(lives=10, last_regeneration=0.0, maximum=5)
        self.assertEqual(life.available(), 5)
        life.maximum = None
        self.assertEqual(life.available(), 10)


if __name__ == "__main__":
    unittest.main()
