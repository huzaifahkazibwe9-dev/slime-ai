import unittest

from execution_engine import run_dry_simulation
from game_state import GameState, Shooter


class GameStateValidationTests(unittest.TestCase):
    def test_non_list_and_empty_boards_return_errors(self):
        for board in (None, "red", {}, (), []):
            with self.subTest(board=board):
                state = GameState(board=board)
                errors = state.validate()
                self.assertTrue(errors)

    def test_non_list_rows_return_errors_without_raising(self):
        boards = (
            [None],
            [["red"], None],
            [["red"], ("blue",)],
        )
        for board in boards:
            with self.subTest(board=board):
                errors = GameState(board=board).validate()
                self.assertIn("Board rows must be lists", errors)

    def test_empty_and_ragged_rows_return_errors(self):
        empty = GameState(board=[[]]).validate()
        ragged = GameState(board=[["red"], ["blue", "blue"]]).validate()
        self.assertIn("Board must contain at least one column", empty)
        self.assertIn("Board rows have different widths", ragged)

    def test_board_cells_must_be_nonempty_strings_or_none(self):
        for cell in (True, 1, 1.0, "", [], {}):
            with self.subTest(cell=cell):
                errors = GameState(board=[[cell]]).validate()
                self.assertTrue(
                    any("Invalid board cell at" in error for error in errors)
                )

    def test_malformed_shooter_records_return_errors_without_raising(self):
        state = GameState(board=[["red"]], shooters={"R": None})
        self.assertIn("Invalid shooter: R", state.validate())

    def test_shooter_direction_must_be_a_string(self):
        shooter = Shooter("R", "red", 2, direction=["right"])
        state = GameState(board=[["red"]], shooters={"R": shooter})
        self.assertIn("Invalid shooter: R", state.validate())

    def test_malformed_container_fields_return_errors_without_raising(self):
        state = GameState(
            board=[["red"]],
            shooters={},
            conveyor=[[]],
            storage=None,
        )
        errors = state.validate()
        self.assertIn("Conveyor contains an invalid shooter ID", errors)
        self.assertIn("Storage must be a list of shooter IDs", errors)

    def test_unhashable_occupied_ids_do_not_break_validation(self):
        state = GameState(
            board=[["red"]],
            shooters={},
            conveyor=[[]],
            storage=[{}],
        )
        errors = state.validate()
        self.assertTrue(errors)

    def test_dry_run_rejects_malformed_board_with_validation_error(self):
        state = GameState(board=[["red"], None], shooters={})
        with self.assertRaisesRegex(ValueError, "GameState validation failed"):
            run_dry_simulation(state)

    def test_valid_small_state_remains_accepted(self):
        state = GameState(
            board=[["red", None]],
            shooters={
                "R": Shooter(
                    "R", "red", 2, direction="right",
                    x=-1, y=0, accessible=True,
                )
            },
        )
        self.assertEqual(state.validate(), [])


if __name__ == "__main__":
    unittest.main()
