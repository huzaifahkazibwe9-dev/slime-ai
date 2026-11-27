import copy
import json
import unittest
from pathlib import Path

from bonded_group_simulator import simulate_bonded_group
from game_state import GameState, Shooter


FIXTURE_PATH = (
    Path(__file__).parent / "data" / "bonded_group_invalid_reference_cases.json"
)


class InvalidBondedGroupReferenceCasesTests(unittest.TestCase):
    def load_fixture(self):
        with FIXTURE_PATH.open(encoding="utf-8") as handle:
            return json.load(handle)

    def assert_exact_keys(self, value, expected, label):
        self.assertIsInstance(value, dict, label)
        self.assertEqual(set(value), set(expected), label)

    def test_negative_fixture_has_exact_schema_and_intentional_malformed_values(self):
        fixture = self.load_fixture()
        self.assert_exact_keys(
            fixture, {"schema_version", "purpose", "cases"}, "top-level"
        )
        self.assertIs(type(fixture["schema_version"]), int)
        self.assertEqual(fixture["schema_version"], 1)
        self.assertIsInstance(fixture["purpose"], str)
        self.assertTrue(fixture["purpose"].strip())
        self.assertIsInstance(fixture["cases"], list)
        self.assertGreaterEqual(len(fixture["cases"]), 5)

        case_ids = []
        for case in fixture["cases"]:
            self.assert_exact_keys(
                case,
                {
                    "id", "board", "shooters", "start_shooter_id",
                    "expected_validation_errors", "expected_group",
                    "expected_group_id", "expected_selectable",
                },
                "case",
            )
            self.assertIsInstance(case["id"], str)
            self.assertTrue(case["id"].strip())
            case_ids.append(case["id"])

            board = case["board"]
            self.assertIsInstance(board, list)
            self.assertTrue(board)
            self.assertTrue(all(isinstance(row, list) and row for row in board))
            width = len(board[0])
            self.assertTrue(all(len(row) == width for row in board))
            for row in board:
                for cell in row:
                    self.assertTrue(
                        cell is None or (
                            isinstance(cell, str) and bool(cell.strip())
                        )
                    )

            self.assertIsInstance(case["shooters"], list)
            self.assertTrue(case["shooters"])
            shooter_ids = []
            for shooter in case["shooters"]:
                self.assert_exact_keys(
                    shooter,
                    {
                        "id", "color", "ammo", "direction", "x", "y",
                        "accessible", "group_id", "bonded_ids",
                    },
                    "shooter",
                )
                self.assertIsInstance(shooter["id"], str)
                self.assertTrue(shooter["id"].strip())
                shooter_ids.append(shooter["id"])
                self.assertIsInstance(shooter["color"], str)
                self.assertTrue(shooter["color"].strip())
                self.assertIs(type(shooter["ammo"]), int)
                self.assertGreaterEqual(shooter["ammo"], 0)
                self.assertIsInstance(shooter["direction"], str)
                self.assertIs(type(shooter["x"]), int)
                self.assertIs(type(shooter["y"]), int)
                self.assertIs(type(shooter["accessible"]), bool)
                self.assertTrue(
                    shooter["group_id"] is None
                    or (
                        isinstance(shooter["group_id"], str)
                        and bool(shooter["group_id"].strip())
                    )
                )
                # The negative corpus deliberately allows a null container or
                # non-string member here; GameState validation must reject it.
                self.assertTrue(
                    shooter["bonded_ids"] is None
                    or isinstance(shooter["bonded_ids"], list)
                )
                if isinstance(shooter["bonded_ids"], list):
                    self.assertTrue(all(
                        member is None
                        or (isinstance(member, str) and bool(member.strip()))
                        for member in shooter["bonded_ids"]
                    ))
                    strings = [
                        member for member in shooter["bonded_ids"]
                        if isinstance(member, str)
                    ]
                    self.assertEqual(len(strings), len(set(strings)))
                self.assertNotIn(shooter["id"], shooter["bonded_ids"] or [])

            self.assertEqual(len(shooter_ids), len(set(shooter_ids)))
            self.assertIsInstance(case["start_shooter_id"], str)
            self.assertIn(case["start_shooter_id"], shooter_ids)
            errors = case["expected_validation_errors"]
            self.assertIsInstance(errors, list)
            self.assertTrue(errors)
            self.assertTrue(all(
                isinstance(error, str) and bool(error.strip())
                for error in errors
            ))
            self.assertIsInstance(case["expected_group"], list)
            self.assertTrue(all(
                isinstance(member, str) and member in shooter_ids
                for member in case["expected_group"]
            ))
            self.assertTrue(
                case["expected_group_id"] is None
                or (
                    isinstance(case["expected_group_id"], str)
                    and bool(case["expected_group_id"].strip())
                )
            )
            self.assertIs(type(case["expected_selectable"]), bool)
            self.assertFalse(case["expected_selectable"])

        self.assertEqual(len(case_ids), len(set(case_ids)))

    def test_invalid_bonded_group_states_fail_closed_without_mutation(self):
        fixture = self.load_fixture()
        for case in fixture["cases"]:
            with self.subTest(case=case["id"]):
                shooters = {
                    item["id"]: Shooter(
                        id=item["id"],
                        color=item["color"],
                        ammo=item["ammo"],
                        direction=item["direction"],
                        x=item["x"],
                        y=item["y"],
                        accessible=item["accessible"],
                        group_id=item["group_id"],
                        bonded_ids=(
                            None if item["bonded_ids"] is None
                            else list(item["bonded_ids"])
                        ),
                    )
                    for item in case["shooters"]
                }
                state = GameState(
                    board=[list(row) for row in case["board"]],
                    shooters=shooters,
                )
                before = copy.deepcopy(state)

                errors = state.validate()
                self.assertEqual(errors, case["expected_validation_errors"])
                self.assertEqual(
                    state.bonded_group(case["start_shooter_id"]),
                    case["expected_group"],
                )
                self.assertEqual(
                    state.bonded_group_id(case["start_shooter_id"]),
                    case["expected_group_id"],
                )
                self.assertEqual(
                    state.can_select_group(case["start_shooter_id"]),
                    case["expected_selectable"],
                )
                self.assertFalse(
                    state.select_group(case["start_shooter_id"])
                )
                self.assertEqual(state, before)

                with self.assertRaisesRegex(ValueError, "Invalid GameState"):
                    simulate_bonded_group(state, case["start_shooter_id"])
                self.assertEqual(state, before)


if __name__ == "__main__":
    unittest.main()
