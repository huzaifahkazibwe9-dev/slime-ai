import copy
import json
import unittest
from pathlib import Path

from execution_engine import run_dry_simulation
from game_state import GameState, Shooter


REFERENCE_PATH = (
    Path(__file__).resolve().parent
    / "data"
    / "solver_outcome_reference_cases.json"
)


class SolverOutcomeReferenceCaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reference = json.loads(REFERENCE_PATH.read_text(encoding="utf-8"))

    def test_reference_fixture_has_exact_schema(self):
        self.assertIsInstance(self.reference, dict)
        self.assertEqual(
            set(self.reference), {"schema_version", "purpose", "cases"}
        )
        self.assertIs(type(self.reference["schema_version"]), int)
        self.assertEqual(self.reference["schema_version"], 1)
        self.assertIsInstance(self.reference["purpose"], str)
        self.assertTrue(self.reference["purpose"].strip())
        self.assertIsInstance(self.reference["cases"], list)
        self.assertGreaterEqual(len(self.reference["cases"]), 1)

        case_ids = []
        expected_fields = {
            "status", "raises", "accessible_group_count",
            "candidates_examined", "search_truncated", "best",
            "source_state_unchanged", "evidence_verified",
            "live_execution_allowed", "gameplay_actions_performed",
        }
        for case in self.reference["cases"]:
            with self.subTest(case=case.get("id")):
                self.assertEqual(
                    set(case),
                    {
                        "id", "board", "shooter",
                        "provenance_verified", "expected",
                    },
                )
                self.assertIsInstance(case["id"], str)
                self.assertTrue(case["id"].strip())
                case_ids.append(case["id"])

                board = case["board"]
                self.assertIsInstance(board, list)
                self.assertTrue(board)
                for row in board:
                    self.assertIsInstance(row, list)
                    self.assertTrue(row)
                    for cell in row:
                        self.assertTrue(
                            cell is None
                            or (isinstance(cell, str) and bool(cell))
                        )

                shooter = case["shooter"]
                self.assertEqual(
                    set(shooter),
                    {"id", "color", "ammo", "direction", "x", "y", "accessible"},
                )
                self.assertIsInstance(shooter["id"], str)
                self.assertTrue(shooter["id"])
                self.assertIsInstance(shooter["color"], str)
                self.assertTrue(shooter["color"])
                self.assertIs(type(shooter["ammo"]), int)
                self.assertGreaterEqual(shooter["ammo"], 0)
                self.assertIn(shooter["direction"], ("up", "down", "left", "right"))
                self.assertIs(type(shooter["x"]), int)
                self.assertIs(type(shooter["y"]), int)
                self.assertIs(type(shooter["accessible"]), bool)
                self.assertTrue(
                    case["provenance_verified"] is None
                    or type(case["provenance_verified"]) is bool
                )

                expected = case["expected"]
                self.assertEqual(set(expected), expected_fields)
                self.assertTrue(
                    expected["status"] is None
                    or isinstance(expected["status"], str)
                )
                self.assertTrue(
                    expected["raises"] is None
                    or isinstance(expected["raises"], str)
                )
                for name in ("accessible_group_count", "candidates_examined"):
                    value = expected[name]
                    self.assertTrue(value is None or type(value) is int)
                    if value is not None:
                        self.assertGreaterEqual(value, 0)
                for name in (
                    "search_truncated", "source_state_unchanged",
                    "evidence_verified", "live_execution_allowed",
                    "gameplay_actions_performed",
                ):
                    value = expected[name]
                    self.assertTrue(value is None or type(value) is bool)

                best = expected["best"]
                if best is not None:
                    self.assertEqual(
                        set(best),
                        {"pixels_removed", "remaining_pixels", "blocked_attempts"},
                    )
                    for value in best.values():
                        self.assertIs(type(value), int)
                        self.assertGreaterEqual(value, 0)

                if expected["raises"] is not None:
                    self.assertIsNone(expected["status"])
                    self.assertIsNone(best)
                    self.assertIsNone(expected["candidates_examined"])
                    self.assertFalse(
                        all(
                            expected[field] is not None
                            for field in (
                                "search_truncated",
                                "source_state_unchanged",
                                "evidence_verified",
                                "live_execution_allowed",
                                "gameplay_actions_performed",
                            )
                        )
                    )
                else:
                    self.assertIsNone(expected["raises"])
                    self.assertIsInstance(expected["status"], str)

        self.assertEqual(len(case_ids), len(set(case_ids)))

    def test_dry_run_outcomes_match_reference_cases(self):
        for case in self.reference["cases"]:
            with self.subTest(case=case["id"]):
                shooter = Shooter(**case["shooter"])
                state = GameState(
                    board=copy.deepcopy(case["board"]),
                    shooters={shooter.id: shooter},
                )
                if case["provenance_verified"] is not None:
                    state.shooter_capture_provenance_verified = (
                        case["provenance_verified"]
                    )
                before = copy.deepcopy(state)
                expected = case["expected"]

                if expected["raises"] is not None:
                    with self.assertRaisesRegex(
                        ValueError, expected["raises"]
                    ):
                        run_dry_simulation(state)
                    self.assertEqual(state, before)
                    continue

                report = run_dry_simulation(state)
                for field in (
                    "status", "accessible_group_count", "candidates_examined",
                    "search_truncated", "source_state_unchanged",
                    "evidence_verified", "live_execution_allowed",
                    "gameplay_actions_performed",
                ):
                    self.assertEqual(report[field], expected[field], field)

                if expected["best"] is None:
                    self.assertIsNone(report["best"])
                else:
                    self.assertIsInstance(report["best"], dict)
                    for field, value in expected["best"].items():
                        self.assertEqual(report["best"][field], value, field)

                self.assertEqual(state, before)


if __name__ == "__main__":
    unittest.main(verbosity=2)
