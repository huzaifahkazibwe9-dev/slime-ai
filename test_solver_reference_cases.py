import copy
import json
import unittest
from pathlib import Path

from game_state import GameState, Shooter
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
