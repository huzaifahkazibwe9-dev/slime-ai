import copy
import json
import unittest
from pathlib import Path

from game_state import GameState, Shooter


FIXTURE_PATH = (
    Path(__file__).parent / "data" / "bonded_group_selectability_cases.json"
)


class BondedGroupSelectabilityCasesTests(unittest.TestCase):
    def load_fixture(self):
        with FIXTURE_PATH.open(encoding="utf-8") as handle:
            return json.load(handle)

    def assert_exact_keys(self, value, expected, label):
        self.assertIsInstance(value, dict, label)
        self.assertEqual(set(value), set(expected), label)

    def build_state(self, case):
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
                bonded_ids=list(item["bonded_ids"]),
            )
            for item in case["shooters"]
        }
        return GameState(
            board=[list(row) for row in case["board"]],
            shooters=shooters,
            conveyor=list(case["conveyor"]),
            storage=list(case["storage"]),
        )

    def test_selectability_fixture_has_exact_schema(self):
        fixture = self.load_fixture()
        self.assert_exact_keys(
            fixture, {"schema_version", "purpose", "cases"}, "top-level"
        )
        self.assertIs(type(fixture["schema_version"]), int)
        self.assertEqual(fixture["schema_version"], 1)
        self.assertIsInstance(fixture["purpose"], str)
        self.assertTrue(fixture["purpose"].strip())
        self.assertIsInstance(fixture["cases"], list)
        self.assertGreaterEqual(len(fixture["cases"]), 8)

        case_ids = []
        for case in fixture["cases"]:
            self.assert_exact_keys(
                case,
                {
                    "id", "board", "shooters", "conveyor", "storage",
                    "start_shooter_id", "expected_validation_errors",
                    "expected_group", "expected_group_id",
                    "expected_selectable", "expected_selection_succeeds",
                    "expected_conveyor_after_selection",
                    "expected_storage_after_selection",
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
                        cell is None
                        or (isinstance(cell, str) and bool(cell.strip()))
                    )

            self.assertIsInstance(case["shooters"], list)
            self.assertTrue(case["shooters"])
            shooter_ids = []
            for item in case["shooters"]:
                self.assert_exact_keys(
                    item,
                    {
                        "id", "color", "ammo", "direction", "x", "y",
                        "accessible", "group_id", "bonded_ids",
                    },
                    "shooter",
                )
                self.assertIsInstance(item["id"], str)
                self.assertTrue(item["id"].strip())
                shooter_ids.append(item["id"])
                self.assertIsInstance(item["color"], str)
                self.assertTrue(item["color"].strip())
                self.assertIs(type(item["ammo"]), int)
                self.assertGreaterEqual(item["ammo"], 0)
                self.assertIsInstance(item["direction"], str)
                self.assertIs(type(item["x"]), int)
                self.assertIs(type(item["y"]), int)
                self.assertIs(type(item["accessible"]), bool)
                self.assertTrue(
                    item["group_id"] is None
                    or (
                        isinstance(item["group_id"], str)
                        and bool(item["group_id"].strip())
                    )
                )
                self.assertIsInstance(item["bonded_ids"], list)
                self.assertTrue(all(
                    isinstance(member, str) and bool(member.strip())
                    for member in item["bonded_ids"]
                ))
                # Duplicate entries are intentional in one negative case.
            self.assertEqual(len(shooter_ids), len(set(shooter_ids)))

            for field in ("conveyor", "storage"):
                self.assertIsInstance(case[field], list)
                self.assertTrue(all(
                    isinstance(item, str) and bool(item.strip())
                    for item in case[field]
                ))
            self.assertIsInstance(case["start_shooter_id"], str)
            self.assertIn(case["start_shooter_id"], shooter_ids)
            self.assertTrue(all(
                item in shooter_ids
                for item in case["conveyor"] + case["storage"]
            ))
            errors = case["expected_validation_errors"]
            self.assertIsInstance(errors, list)
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
                or isinstance(case["expected_group_id"], str)
            )
            for field in ("expected_selectable", "expected_selection_succeeds"):
                self.assertIs(type(case[field]), bool)
            self.assertIs(type(case["expected_selectable"]), bool)
            self.assertEqual(
                case["expected_selection_succeeds"],
                case["expected_selectable"],
            )
            for field in (
                "expected_conveyor_after_selection",
                "expected_storage_after_selection",
            ):
                self.assertIsInstance(case[field], list)
                self.assertTrue(all(
                    isinstance(item, str) for item in case[field]
                ))

        self.assertEqual(len(case_ids), len(set(case_ids)))

    def test_capacity_occupancy_and_duplicate_references_fail_closed(self):
        fixture = self.load_fixture()
        for case in fixture["cases"]:
            with self.subTest(case=case["id"]):
                state = self.build_state(case)
                before = copy.deepcopy(state)

                self.assertEqual(
                    state.validate(), case["expected_validation_errors"]
                )
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
                # The selectability check is read-only in both valid and
                # intentionally malformed occupancy/reference states.
                self.assertEqual(state, before)

                selected = state.select_group(case["start_shooter_id"])
                self.assertEqual(
                    selected, case["expected_selection_succeeds"]
                )
                self.assertEqual(
                    state.conveyor, case["expected_conveyor_after_selection"]
                )
                self.assertEqual(
                    state.storage, case["expected_storage_after_selection"]
                )
                if not selected:
                    self.assertEqual(state, before)
                else:
                    self.assertTrue(all(
                        not state.shooters[member].accessible
                        for member in case["expected_group"]
                    ))


if __name__ == "__main__":
    unittest.main()
