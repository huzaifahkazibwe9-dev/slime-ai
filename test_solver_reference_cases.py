import copy
import json
import unittest
from pathlib import Path

from game_state import DIRECTIONS, GameState, Shooter
from solver import simulate_shot


REFERENCE_PATH = (
    Path(__file__).resolve().parent
    / "data"
    / "solver_reference_cases.json"
)


class ShotSimulatorReferenceCaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reference = json.loads(REFERENCE_PATH.read_text(encoding="utf-8"))

    def test_reference_schema_and_case_ids_are_valid(self):
        self.assertEqual(self.reference.get("schema_version"), 1)
        cases = self.reference.get("cases")
        self.assertIsInstance(cases, list)
        self.assertGreaterEqual(len(cases), 1)
        ids = [case.get("id") for case in cases]
        self.assertTrue(all(isinstance(value, str) and value for value in ids))
        self.assertEqual(len(ids), len(set(ids)))

    def test_reference_cases_have_exact_types_and_complete_shapes(self):
        self.assertIsInstance(self.reference, dict)
        self.assertEqual(
            set(self.reference),
            {"schema_version", "purpose", "cases"},
        )
        self.assertIs(type(self.reference["schema_version"]), int)
        self.assertEqual(self.reference["schema_version"], 1)
        self.assertIsInstance(self.reference["purpose"], str)
        self.assertTrue(self.reference["purpose"].strip())

        for case in self.reference["cases"]:
            with self.subTest(case=case.get("id")):
                self.assertEqual(
                    set(case), {"id", "board", "shooter", "steps"}
                )
                board = case["board"]
                self.assertIsInstance(board, list)
                self.assertTrue(board)
                self.assertTrue(all(isinstance(row, list) for row in board))
                width = len(board[0])
                self.assertGreater(width, 0)
                self.assertTrue(all(len(row) == width for row in board))
                for row in board:
                    for cell in row:
                        self.assertTrue(
                            cell is None
                            or (isinstance(cell, str) and bool(cell))
                        )

                shooter = case["shooter"]
                self.assertEqual(
                    set(shooter),
                    {"id", "color", "ammo", "direction", "x", "y"},
                )
                self.assertIsInstance(shooter["id"], str)
                self.assertTrue(shooter["id"])
                self.assertIsInstance(shooter["color"], str)
                self.assertTrue(shooter["color"])
                self.assertTrue(
                    shooter["ammo"] is None
                    or type(shooter["ammo"]) is int
                )
                self.assertIsInstance(shooter["direction"], str)
                self.assertIn(shooter["direction"], DIRECTIONS)
                self.assertIs(type(shooter["x"]), int)
                self.assertIs(type(shooter["y"]), int)

                steps = case["steps"]
                self.assertIsInstance(steps, list)
                self.assertTrue(steps)
                for expected in steps:
                    self.assertEqual(
                        set(expected),
                        {
                            "fired", "removed", "position", "reason",
                            "remaining_ammo", "board",
                        },
                    )
                    self.assertIs(type(expected["fired"]), bool)
                    self.assertIs(type(expected["removed"]), bool)
                    self.assertIsInstance(expected["reason"], str)
                    self.assertTrue(expected["reason"])
                    position = expected["position"]
                    if position is not None:
                        self.assertIsInstance(position, list)
                        self.assertEqual(len(position), 2)
                        self.assertTrue(
                            all(type(value) is int for value in position)
                        )
                    remaining_ammo = expected["remaining_ammo"]
                    self.assertTrue(
                        remaining_ammo is None
                        or (
                            type(remaining_ammo) is int
                            and remaining_ammo >= 0
                        )
                    )
                    expected_board = expected["board"]
                    self.assertIsInstance(expected_board, list)
                    self.assertEqual(len(expected_board), len(board))
                    self.assertTrue(
                        all(
                            isinstance(row, list) and len(row) == width
                            for row in expected_board
                        )
                    )
                    self.assertTrue(
                        all(
                            cell is None
                            or (isinstance(cell, str) and bool(cell))
                            for row in expected_board
                            for cell in row
                        )
                    )

    def test_reference_corpus_covers_all_four_cardinal_directions(self):
        cases = {case["id"]: case for case in self.reference["cases"]}
        expected = {
            "up": "upward_ray_crosses_empty_cell",
            "down": "downward_ray_crosses_empty_cell",
            "left": "leftward_ray_crosses_empty_cell",
            "right": "rightward_ray_crosses_empty_cell",
        }
        for direction, case_id in expected.items():
            with self.subTest(direction=direction):
                self.assertIn(case_id, cases)
                self.assertEqual(
                    cases[case_id]["shooter"]["direction"], direction
                )

    def test_shot_outputs_match_hand_checkable_reference_cases(self):
        for case in self.reference["cases"]:
            with self.subTest(case=case["id"]):
                shooter_data = dict(case["shooter"])
                shooter = Shooter(**shooter_data)
                state = GameState(
                    board=copy.deepcopy(case["board"]),
                    shooters={shooter.id: shooter},
                )
                for step_number, expected in enumerate(case["steps"], start=1):
                    result = simulate_shot(state, shooter.id)
                    self.assertEqual(
                        result.fired, expected["fired"],
                        f"{case['id']} step {step_number} fired",
                    )
                    self.assertEqual(
                        result.removed, expected["removed"],
                        f"{case['id']} step {step_number} removed",
                    )
                    expected_position = expected["position"]
                    if expected_position is not None:
                        expected_position = tuple(expected_position)
                    self.assertEqual(
                        result.position, expected_position,
                        f"{case['id']} step {step_number} position",
                    )
                    self.assertEqual(
                        result.reason, expected["reason"],
                        f"{case['id']} step {step_number} reason",
                    )
                    self.assertEqual(
                        shooter.ammo, expected["remaining_ammo"],
                        f"{case['id']} step {step_number} ammunition",
                    )
                    self.assertEqual(
                        state.board, expected["board"],
                        f"{case['id']} step {step_number} board",
                    )


if __name__ == "__main__":
    unittest.main(verbosity=2)
