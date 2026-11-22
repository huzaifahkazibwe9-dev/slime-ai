import unittest

from observation_pipeline import evaluate_observations


def observation(board, image_size=(1080, 2220),
                grid_size=(35, 35), bounds=(201, 431, 881, 1113)):
    return {
        "board": board,
        "image_size": list(image_size),
        "grid_size": list(grid_size),
        "bounds": list(bounds),
    }


class ObservationPipelineTests(unittest.TestCase):
    def setUp(self):
        self.board = [["white"] * 5 for _ in range(5)]

    def test_unchanged_board(self):
        result = evaluate_observations(
            observation(self.board),
            observation([row[:] for row in self.board]),
        )
        self.assertEqual(result["status"], "NO_BOARD_CHANGE")

    def test_uniform_edge_changes_rejected(self):
        changed = [row[:] for row in self.board]
        changed[0] = ["green"] * 5
        result = evaluate_observations(
            observation(self.board), observation(changed)
        )
        self.assertEqual(
            result["status"], "REJECTED_SUSPICIOUS_EDGE_CHANGE"
        )

    def test_interior_changes_need_review(self):
        changed = [row[:] for row in self.board]
        changed[2][2] = "green"
        result = evaluate_observations(
            observation(self.board), observation(changed)
        )
        self.assertEqual(
            result["status"], "INTERIOR_CHANGE_NEEDS_REVIEW"
        )

    def test_single_edge_change_needs_review(self):
        changed = [row[:] for row in self.board]
        changed[0][0] = "green"
        result = evaluate_observations(
            observation(self.board), observation(changed)
        )
        self.assertEqual(result["status"], "EDGE_CHANGE_NEEDS_REVIEW")

    def test_different_image_size_rejected(self):
        result = evaluate_observations(
            observation(self.board),
            observation(self.board, image_size=(720, 1280)),
        )
        self.assertEqual(
            result["status"], "REJECTED_INCOMPATIBLE_OBSERVATIONS"
        )

    def test_different_grid_rejected(self):
        result = evaluate_observations(
            observation(self.board),
            observation(self.board, grid_size=(34, 35)),
        )
        self.assertEqual(
            result["status"], "REJECTED_INCOMPATIBLE_OBSERVATIONS"
        )

    def test_tile_removals_never_claimed_verified(self):
        changed = [row[:] for row in self.board]
        changed[2][2] = "green"
        result = evaluate_observations(
            observation(self.board), observation(changed)
        )
        self.assertFalse(result["transition_verified"])
        self.assertFalse(result["tile_removals_verified"])
        self.assertFalse(result["game_taps_enabled"])

    def test_incompatible_observation_keeps_safety_flags_false(self):
        result = evaluate_observations(
            observation(self.board),
            observation(self.board, image_size=(720, 1280)),
        )
        self.assertFalse(result["transition_verified"])
        self.assertFalse(result["tile_removals_verified"])
        self.assertFalse(result["game_taps_enabled"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
