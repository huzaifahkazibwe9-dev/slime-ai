import json
import unittest
from pathlib import Path

from bonded_group_simulator import simulate_bonded_group
from game_state import DIRECTIONS, GameState, Shooter


FIXTURE_PATH = Path(__file__).parent / "data" / "bonded_group_reference_cases.json"


class BondedGroupReferenceCasesTests(unittest.TestCase):
    def load_fixture(self):
        with FIXTURE_PATH.open(encoding="utf-8") as handle:
            return json.load(handle)

    def assert_exact_keys(self, value, expected, label):
        self.assertIsInstance(value, dict, label)
        self.assertEqual(set(value), set(expected), label)

    def test_reference_fixture_has_exact_schema_and_valid_case_types(self):
        fixture = self.load_fixture()
        self.assert_exact_keys(
            fixture, {"schema_version", "purpose", "cases"}, "top-level"
        )
        self.assertIs(type(fixture["schema_version"]), int)
        self.assertEqual(fixture["schema_version"], 1)
        self.assertIsInstance(fixture["purpose"], str)
        self.assertTrue(fixture["purpose"].strip())
        self.assertIsInstance(fixture["cases"], list)
        self.assertTrue(fixture["cases"])

        case_ids = []
        for case in fixture["cases"]:
            self.assert_exact_keys(
                case,
                {"id", "board", "shooters", "conveyor", "start_shooter_id", "expected"},
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
                self.assertIn(shooter["direction"], DIRECTIONS)
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
                self.assertIsInstance(shooter["bonded_ids"], list)
                self.assertTrue(
                    all(
                        isinstance(member, str) and bool(member.strip())
                        for member in shooter["bonded_ids"]
                    )
                )
                self.assertEqual(
                    len(shooter["bonded_ids"]),
                    len(set(shooter["bonded_ids"])),
                )
                self.assertNotIn(shooter["id"], shooter["bonded_ids"])

            self.assertEqual(len(shooter_ids), len(set(shooter_ids)))
            self.assertIsInstance(case["start_shooter_id"], str)
            self.assertIn(case["start_shooter_id"], shooter_ids)
            self.assertIsInstance(case["conveyor"], list)
            self.assertTrue(all(
                isinstance(item, str) and item in shooter_ids
                for item in case["conveyor"]
            ))
            self.assertEqual(len(case["conveyor"]), len(set(case["conveyor"])))

            expected = case["expected"]
            self.assert_exact_keys(
                expected,
                {
                    "status", "shooter_ids", "group_selected_atomically",
                    "conveyor_after_selection", "initial_pixels",
                    "remaining_pixels", "pixels_removed", "final_board",
                    "remaining_ammo", "member_reports", "source_state_unchanged",
                    "gameplay_verified", "live_execution_allowed",
                    "gameplay_actions_performed", "game_taps_enabled",
                },
                "expected",
            )
            self.assertEqual(expected["status"], "SIMULATED")
            self.assertIs(type(expected["group_selected_atomically"]), bool)
            self.assertTrue(expected["group_selected_atomically"])
            for name in (
                "source_state_unchanged", "gameplay_verified",
                "live_execution_allowed", "gameplay_actions_performed",
                "game_taps_enabled",
            ):
                self.assertIs(type(expected[name]), bool)
            self.assertTrue(expected["source_state_unchanged"])
            self.assertFalse(expected["gameplay_verified"])
            self.assertFalse(expected["live_execution_allowed"])
            self.assertFalse(expected["gameplay_actions_performed"])
            self.assertFalse(expected["game_taps_enabled"])

            for name in ("initial_pixels", "remaining_pixels", "pixels_removed"):
                self.assertIs(type(expected[name]), int)
                self.assertGreaterEqual(expected[name], 0)
            self.assertEqual(
                expected["initial_pixels"],
                expected["remaining_pixels"] + expected["pixels_removed"],
            )
            self.assertIsInstance(expected["final_board"], list)
            self.assertEqual(len(expected["final_board"]), len(board))
            self.assertTrue(all(
                isinstance(row, list) and len(row) == width
                for row in expected["final_board"]
            ))
            for row in expected["final_board"]:
                for cell in row:
                    self.assertTrue(
                        cell is None or (
                            isinstance(cell, str) and bool(cell.strip())
                        )
                    )
            self.assertIsInstance(expected["remaining_ammo"], dict)
            self.assertTrue(all(
                isinstance(key, str)
                and type(value) is int
                and value >= 0
                for key, value in expected["remaining_ammo"].items()
            ))
            self.assertIsInstance(expected["member_reports"], list)
            self.assertEqual(expected["shooter_ids"], sorted(expected["shooter_ids"]))
            self.assertEqual(
                expected["conveyor_after_selection"],
                case["conveyor"] + expected["shooter_ids"],
            )
            self.assertEqual(
                set(expected["remaining_ammo"]),
                set(expected["shooter_ids"]),
            )

            member_ids = []
            for member in expected["member_reports"]:
                self.assert_exact_keys(
                    member,
                    {
                        "shooter_id", "initial_ammo", "remaining_ammo",
                        "shots_attempted", "pixels_removed", "steps",
                    },
                    "member report",
                )
                self.assertIsInstance(member["shooter_id"], str)
                member_ids.append(member["shooter_id"])
                for name in (
                    "initial_ammo", "remaining_ammo", "shots_attempted",
                    "pixels_removed",
                ):
                    self.assertIs(type(member[name]), int)
                    self.assertGreaterEqual(member[name], 0)
                self.assertIsInstance(member["steps"], list)
                self.assertEqual(member["shots_attempted"], len(member["steps"]))
                self.assertEqual(
                    member["initial_ammo"] - member["remaining_ammo"],
                    member["pixels_removed"],
                )
                for step in member["steps"]:
                    self.assert_exact_keys(
                        step,
                        {
                            "shot_number", "fired", "removed", "position",
                            "reason", "ammo_remaining",
                        },
                        "member step",
                    )
                    self.assertIs(type(step["shot_number"]), int)
                    self.assertIs(type(step["fired"]), bool)
                    self.assertIs(type(step["removed"]), bool)
                    self.assertTrue(
                        step["position"] is None
                        or (
                            isinstance(step["position"], list)
                            and len(step["position"]) == 2
                            and all(type(value) is int for value in step["position"])
                        )
                    )
                    self.assertIsInstance(step["reason"], str)
                    self.assertTrue(step["reason"].strip())
                    self.assertIs(type(step["ammo_remaining"]), int)
            self.assertEqual(member_ids, expected["shooter_ids"])

        self.assertEqual(len(case_ids), len(set(case_ids)))

    def test_bonded_group_outcomes_match_hand_checkable_reference_cases(self):
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
                        bonded_ids=list(item["bonded_ids"]),
                    )
                    for item in case["shooters"]
                }
                state = GameState(
                    board=[list(row) for row in case["board"]],
                    shooters=shooters,
                    conveyor=list(case["conveyor"]),
                )
                before = GameState(
                    board=[list(row) for row in state.board],
                    shooters={
                        key: Shooter(
                            id=value.id,
                            color=value.color,
                            ammo=value.ammo,
                            direction=value.direction,
                            x=value.x,
                            y=value.y,
                            accessible=value.accessible,
                            group_id=value.group_id,
                            bonded_ids=list(value.bonded_ids),
                        )
                        for key, value in state.shooters.items()
                    },
                    conveyor=list(state.conveyor),
                )

                self.assertEqual(state.validate(), [])
                report = simulate_bonded_group(
                    state, case["start_shooter_id"]
                )
                expected = case["expected"]

                for name in (
                    "status", "shooter_ids", "group_selected_atomically",
                    "conveyor_after_selection", "initial_pixels",
                    "remaining_pixels", "pixels_removed", "final_board",
                    "remaining_ammo", "source_state_unchanged",
                    "gameplay_verified", "live_execution_allowed",
                    "gameplay_actions_performed", "game_taps_enabled",
                ):
                    self.assertEqual(report[name], expected[name], name)

                self.assertEqual(state, before)
                self.assertEqual(len(report["member_reports"]), len(expected["member_reports"]))
                for actual_member, expected_member in zip(
                    report["member_reports"], expected["member_reports"]
                ):
                    for name in (
                        "shooter_id", "initial_ammo", "remaining_ammo",
                        "shots_attempted", "pixels_removed",
                    ):
                        self.assertEqual(
                            actual_member[name], expected_member[name],
                            f"{actual_member['shooter_id']} {name}",
                        )
                    actual_steps = [
                        {
                            "shot_number": step["shot_number"],
                            "fired": step["fired"],
                            "removed": step["removed"],
                            "position": step["position"],
                            "reason": step["reason"],
                            "ammo_remaining": step["ammo_remaining"],
                        }
                        for step in actual_member["steps"]
                    ]
                    self.assertEqual(actual_steps, expected_member["steps"])


if __name__ == "__main__":
    unittest.main()
