import unittest
from rgb_transition_audit import audit_rgb


def observation(board, size=(1080, 2220), grid=(5, 5)):
    return {
        "image_size": list(size),
        "grid_size": list(grid),
        "bounds": [0, 0, 100, 100],
        "raw_rgb": board,
    }


class RGBTransitionTests(unittest.TestCase):
    def setUp(self):
        self.board = [
            [[255, 255, 255] for _ in range(5)]
            for _ in range(5)
        ]

    def test_unchanged_rgb(self):
        result = audit_rgb(
            observation(self.board),
            observation([[cell[:] for cell in row] for row in self.board]),
        )
        self.assertEqual(result["status"], "NO_SIGNIFICANT_RGB_CHANGE")

    def test_interior_rgb_change_detected(self):
        changed = [[cell[:] for cell in row] for row in self.board]
        changed[2][2] = [0, 255, 0]
        result = audit_rgb(observation(self.board), observation(changed))
        self.assertEqual(result["interior_changes"], 1)
        self.assertEqual(result["status"], "INTERIOR_RGB_CHANGES_DETECTED")

    def test_edge_rgb_change_detected(self):
        changed = [[cell[:] for cell in row] for row in self.board]
        changed[0][0] = [0, 255, 0]
        result = audit_rgb(observation(self.board), observation(changed))
        self.assertEqual(result["edge_changes"], 1)
        self.assertEqual(result["status"], "EDGE_RGB_CHANGES_ONLY")

    def test_small_rgb_change_below_threshold(self):
        changed = [[cell[:] for cell in row] for row in self.board]
        changed[2][2] = [245, 255, 255]
        result = audit_rgb(observation(self.board), observation(changed))
        self.assertEqual(result["changed_cells"], 0)

    def test_different_dimensions_rejected(self):
        with self.assertRaises(ValueError):
            audit_rgb(
                observation(self.board),
                observation(self.board, size=(720, 1280)),
            )

    def test_safety_flags_remain_false(self):
        changed = [[cell[:] for cell in row] for row in self.board]
        changed[2][2] = [0, 255, 0]
        result = audit_rgb(observation(self.board), observation(changed))
        self.assertFalse(result["visual_transition_verified"])
        self.assertFalse(result["tile_removals_verified"])
        self.assertFalse(result["game_taps_enabled"])

    def test_boolean_rgb_channel_raises(self):
        bad = [[cell[:] for cell in row] for row in self.board]
        bad[1][1] = [True, 255, 255]
        with self.assertRaises(ValueError):
            audit_rgb(observation(self.board), observation(bad))

    def test_non_numeric_rgb_channel_raises(self):
        bad = [[cell[:] for cell in row] for row in self.board]
        bad[1][1] = [255, "x", 255]
        with self.assertRaises(ValueError):
            audit_rgb(observation(self.board), observation(bad))

    def test_non_finite_rgb_channel_raises(self):
        for bad_channel in (float("inf"), float("-inf"), float("nan")):
            bad = [[cell[:] for cell in row] for row in self.board]
            bad[2][2] = [bad_channel, 255, 255]
            with self.assertRaises(ValueError):
                audit_rgb(observation(self.board), observation(bad))

    def test_wrong_length_rgb_raises(self):
        bad = [[cell[:] for cell in row] for row in self.board]
        bad[0][0] = [255, 255]
        with self.assertRaises(ValueError):
            audit_rgb(observation(self.board), observation(bad))

    def test_non_list_rgb_sample_raises(self):
        bad = [[cell[:] for cell in row] for row in self.board]
        bad[3][3] = "not-a-list"
        with self.assertRaises(ValueError):
            audit_rgb(observation(self.board), observation(bad))


if __name__ == "__main__":
    unittest.main(verbosity=2)
