import unittest
from edge_change_guard import inspect_edge_changes


class EdgeChangeGuardTests(unittest.TestCase):
    def setUp(self):
        self.old = [["white"] * 5 for _ in range(5)]

    def test_unchanged_board(self):
        result = inspect_edge_changes(self.old, self.old)
        self.assertEqual(result["status"], "UNCHANGED")
        self.assertEqual(result["changed_cells"], 0)

    def test_uniform_edge_changes_flagged(self):
        new = [row[:] for row in self.old]
        new[4][0] = "green"
        new[4][1] = "green"
        new[4][2] = "green"

        result = inspect_edge_changes(self.old, new)
        self.assertEqual(
            result["status"], "SUSPICIOUS_EDGE_ONLY_CHANGE"
        )
        self.assertEqual(result["edge_changes"], 3)
        self.assertEqual(result["interior_changes"], 0)

    def test_interior_change_not_misclassified_as_overlay(self):
        new = [row[:] for row in self.old]
        new[2][2] = "green"

        result = inspect_edge_changes(self.old, new)
        self.assertEqual(
            result["status"], "INTERIOR_CHANGE_REQUIRES_VALIDATION"
        )

    def test_mixed_edge_replacements_not_uniform(self):
        new = [row[:] for row in self.old]
        new[4][0] = "green"
        new[4][1] = "blue"
        new[4][2] = "green"

        result = inspect_edge_changes(self.old, new)
        self.assertFalse(result["uniform_edge_replacement"])
        self.assertNotEqual(
            result["status"], "SUSPICIOUS_EDGE_ONLY_CHANGE"
        )

    def test_safety_flags_always_disabled(self):
        result = inspect_edge_changes(self.old, self.old)
        self.assertFalse(result["board_transition_verified"])
        self.assertFalse(result["game_taps_enabled"])

    def test_rejects_non_rectangular_board(self):
        with self.assertRaises(ValueError):
            inspect_edge_changes(
                [["white", "white"], ["white"]],
                [["white", "white"], ["white"]],
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
