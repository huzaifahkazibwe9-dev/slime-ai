import unittest
from board_transition_auditor import audit_transition


class BoardTransitionTests(unittest.TestCase):

    def test_removed_tile(self):
        result = audit_transition(
            [["cyan", "white"]], [[None, "white"]]
        )
        self.assertTrue(result["valid"])
        self.assertEqual(result["removed"], 1)

    def test_unchanged_board(self):
        board = [["cyan", "white"]]
        result = audit_transition(board, board)
        self.assertTrue(result["valid"])
        self.assertEqual(result["unchanged"], 2)

    def test_new_tile_rejected(self):
        result = audit_transition(
            [[None, "white"]], [["cyan", "white"]]
        )
        self.assertFalse(result["valid"])
        self.assertEqual(result["added"], 1)

    def test_recolouring_rejected(self):
        result = audit_transition([["cyan"]], [["blue"]])
        self.assertFalse(result["valid"])
        self.assertEqual(result["recoloured"], 1)

    def test_wrong_row_count_rejected(self):
        result = audit_transition(
            [["cyan"]], [["cyan"], ["white"]]
        )
        self.assertFalse(result["valid"])

    def test_non_rectangular_board_rejected(self):
        result = audit_transition(
            [["cyan", "white"]], [["cyan"], ["white"]]
        )
        self.assertFalse(result["valid"])

    def test_multiple_removals_counted(self):
        result = audit_transition(
            [["cyan", "white"], ["blue", "red"]],
            [[None, "white"], [None, None]]
        )
        self.assertTrue(result["valid"])
        self.assertEqual(result["removed"], 3)
        self.assertEqual(result["after_occupied"], 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
