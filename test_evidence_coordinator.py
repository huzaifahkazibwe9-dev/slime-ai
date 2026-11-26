import unittest
from evidence_coordinator import audit_transition


class EvidenceCoordinatorTests(unittest.TestCase):

    def test_unchanged_board(self):
        board = [["white", "blue"], ["red", "green"]]
        result = audit_transition(board, board)
        self.assertEqual(result["status"], "UNCHANGED")

    def test_uniform_edge_change_is_suspicious(self):
        before = [["white"] * 5 for _ in range(5)]
        after = [row[:] for row in before]
        after[0][0] = "green"
        after[0][1] = "green"
        after[0][2] = "green"

        result = audit_transition(before, after)
        self.assertEqual(result["status"], "SUSPICIOUS_EDGE_ONLY_CHANGE")
        self.assertEqual(result["edge_changes"], 3)
        self.assertEqual(result["interior_changes"], 0)

    def test_second_border_layer_is_edge(self):
        before = [["white"] * 5 for _ in range(5)]
        after = [row[:] for row in before]
        after[1][2] = "green"

        result = audit_transition(before, after)

        self.assertEqual(result["edge_changes"], 1)
        self.assertEqual(result["interior_changes"], 0)
        self.assertEqual(result["status"], "EDGE_CHANGE_REQUIRES_REVIEW")

    def test_third_row_of_35_grid_is_interior(self):
        before = [["white"] * 35 for _ in range(35)]
        after = [row[:] for row in before]
        after[2][17] = "green"

        result = audit_transition(before, after)

        self.assertEqual(result["edge_changes"], 0)
        self.assertEqual(result["interior_changes"], 1)
        self.assertEqual(
            result["status"], "INTERIOR_CHANGE_REQUIRES_REVIEW"
        )

    def test_second_column_is_edge(self):
        before = [["white"] * 35 for _ in range(35)]
        after = [row[:] for row in before]
        after[17][1] = "green"

        result = audit_transition(before, after)

        self.assertEqual(result["edge_changes"], 1)
        self.assertEqual(result["interior_changes"], 0)

    def test_interior_change_requires_review(self):
        before = [["white"] * 5 for _ in range(5)]
        after = [row[:] for row in before]
        after[2][2] = "green"

        result = audit_transition(before, after)
        self.assertEqual(result["status"], "INTERIOR_CHANGE_REQUIRES_REVIEW")

    def test_mixed_edge_change_requires_review(self):
        before = [["white"] * 5 for _ in range(5)]
        after = [row[:] for row in before]
        after[0][0] = "green"

        result = audit_transition(before, after)
        self.assertEqual(result["status"], "EDGE_CHANGE_REQUIRES_REVIEW")

    def test_safety_flags_remain_false(self):
        board = [["white"] * 3 for _ in range(3)]
        result = audit_transition(board, board)
        self.assertFalse(result["transition_verified"])
        self.assertFalse(result["tile_removals_verified"])
        self.assertFalse(result["game_taps_enabled"])

    def test_dimension_mismatch_rejected(self):
        with self.assertRaises(ValueError):
            audit_transition([["a"]], [["a", "b"]])

    def test_non_rectangular_board_rejected(self):
        with self.assertRaises(ValueError):
            audit_transition(
                [["a", "b"], ["c"]],
                [["a", "b"], ["c", "d"]],
            )

    def test_non_uniform_edge_changes_require_review(self):
        before = [["white"] * 5 for _ in range(5)]
        after = [row[:] for row in before]
        after[0][0] = "green"
        after[0][1] = "blue"
        after[0][2] = "red"

        result = audit_transition(before, after)
        self.assertEqual(result["status"], "EDGE_CHANGE_REQUIRES_REVIEW")
        self.assertFalse(result["uniform_edge_replacement"])
        self.assertEqual(result["edge_changes"], 3)
        self.assertEqual(result["interior_changes"], 0)

    def test_too_small_board_for_edge_width_rejected(self):
        # EDGE_WIDTH = 2, so boards smaller than 5x5 cannot use the edge classifier
        before = [["a"] * 4 for _ in range(4)]
        after = [row[:] for row in before]
        after[0][0] = "b"  # force an edge check
        with self.assertRaises(ValueError):
            audit_transition(before, after)

    def test_empty_board_rejected(self):
        with self.assertRaises(ValueError):
            audit_transition([], [])

if __name__ == "__main__":
    unittest.main()
