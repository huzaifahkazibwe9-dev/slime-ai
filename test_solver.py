import unittest

from game_state import GameState, Shooter
from solver import simulate_shot


class ShotSimulatorTests(unittest.TestCase):
    def test_matching_pixel_is_removed_and_ammo_decreases(self):
        state = GameState(
            board=[[None, "red", None]],
            shooters={"R1": Shooter("R1", "red", 5, "right", -1, 0)},
        )
        result = simulate_shot(state, "R1")
        self.assertTrue(result.fired)
        self.assertTrue(result.removed)
        self.assertEqual(result.position, (1, 0))
        self.assertIsNone(state.board[0][1])
        self.assertEqual(state.shooters["R1"].ammo, 4)

    def test_different_colour_blocks_without_consuming_ammo(self):
        state = GameState(
            board=[["blue", "red", None]],
            shooters={"R1": Shooter("R1", "red", 5, "right", -1, 0)},
        )
        result = simulate_shot(state, "R1")
        self.assertFalse(result.fired)
        self.assertFalse(result.removed)
        self.assertEqual(result.position, (0, 0))
        self.assertEqual(state.board[0], ["blue", "red", None])
        self.assertEqual(state.shooters["R1"].ammo, 5)

    def test_successive_shots_remove_newly_exposed_matching_pixels(self):
        state = GameState(
            board=[["red", "red"]],
            shooters={"R1": Shooter("R1", "red", 5, "right", -1, 0)},
        )
        first = simulate_shot(state, "R1")
        second = simulate_shot(state, "R1")
        self.assertTrue(first.removed)
        self.assertTrue(second.removed)
        self.assertEqual(state.board, [[None, None]])
        self.assertEqual(state.shooters["R1"].ammo, 3)

    def test_unknown_shooter_is_rejected(self):
        state = GameState(board=[["red"]])
        result = simulate_shot(state, "missing")
        self.assertFalse(result.fired)
        self.assertEqual(result.reason, "Unknown shooter")

    def test_unknown_ammunition_is_rejected_without_board_change(self):
        state = GameState(
            board=[["red"]],
            shooters={"R1": Shooter("R1", "red", None, "right", -1, 0)},
        )
        result = simulate_shot(state, "R1")
        self.assertFalse(result.fired)
        self.assertFalse(result.removed)
        self.assertEqual(result.reason, "Ammunition is unknown")
        self.assertEqual(state.board, [["red"]])

    def test_zero_ammunition_is_rejected(self):
        state = GameState(
            board=[["red"]],
            shooters={"R1": Shooter("R1", "red", 0, "right", -1, 0)},
        )
        result = simulate_shot(state, "R1")
        self.assertFalse(result.fired)
        self.assertEqual(result.reason, "No ammunition")
        self.assertEqual(state.board, [["red"]])

    def test_direct_simulator_rejects_malformed_ammunition_types(self):
        for ammo in (True, 1.5, "2", -1):
            with self.subTest(ammo=ammo):
                state = GameState(
                    board=[["red"]],
                    shooters={
                        "R1": Shooter("R1", "red", ammo, "right", -1, 0)
                    },
                )
                result = simulate_shot(state, "R1")
                self.assertFalse(result.fired)
                self.assertFalse(result.removed)
                self.assertEqual(result.reason, "Invalid ammunition")
                self.assertEqual(state.board, [["red"]])

    def test_direct_simulator_rejects_unhashable_direction(self):
        state = GameState(
            board=[["red"]],
            shooters={
                "R1": Shooter("R1", "red", 2, ["right"], -1, 0)
            },
        )
        result = simulate_shot(state, "R1")
        self.assertFalse(result.fired)
        self.assertEqual(result.reason, "Invalid direction")
        self.assertEqual(state.board, [["red"]])

    def test_direct_simulator_rejects_non_integer_coordinates(self):
        for x, y in ((-1.5, 0), (-1, True)):
            with self.subTest(x=x, y=y):
                state = GameState(
                    board=[["red"]],
                    shooters={
                        "R1": Shooter("R1", "red", 2, "right", x, y)
                    },
                )
                result = simulate_shot(state, "R1")
                self.assertFalse(result.fired)
                self.assertEqual(result.reason, "Invalid shooter coordinates")
                self.assertEqual(state.board, [["red"]])

    def test_direct_simulator_rejects_missing_shooter_colour(self):
        state = GameState(
            board=[["red"]],
            shooters={"R1": Shooter("R1", None, 2, "right", -1, 0)},
        )
        result = simulate_shot(state, "R1")
        self.assertFalse(result.fired)
        self.assertEqual(result.reason, "Shooter colour is unknown")
        self.assertEqual(state.board, [["red"]])

    def test_direct_simulator_rejects_malformed_board_structure(self):
        for board in (None, [], [["red"], None], [[True]]):
            with self.subTest(board=board):
                state = GameState(
                    board=board,
                    shooters={"R1": Shooter("R1", "red", 2, "right", -1, 0)},
                )
                result = simulate_shot(state, "R1")
                self.assertFalse(result.fired)
                self.assertEqual(result.reason, "Invalid board structure")

    def test_shooter_validation_rejects_non_integer_board_coordinates(self):
        for x, y in ((-1.5, 0), (-1, True)):
            with self.subTest(x=x, y=y):
                shooter = Shooter("R1", "red", 2, "right", x, y)
                self.assertFalse(shooter.valid())

    def test_invalid_direction_is_rejected(self):
        state = GameState(
            board=[["red"]],
            shooters={"R1": Shooter("R1", "red", 5, "diagonal", -1, 0)},
        )
        result = simulate_shot(state, "R1")
        self.assertFalse(result.fired)
        self.assertEqual(result.reason, "Invalid direction")


if __name__ == "__main__":
    unittest.main(verbosity=2)
