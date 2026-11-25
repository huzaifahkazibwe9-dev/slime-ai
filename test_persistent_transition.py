import unittest
from persistent_transition import persistent_transition


def obs(board):
    return {
        "image_size": [1080, 2220],
        "grid_size": [5, 5],
        "bounds": [1, 1, 99, 99],
        "raw_rgb": board,
    }


def board():
    return [[[255, 255, 255] for _ in range(5)] for _ in range(5)]


class PersistentTransitionTests(unittest.TestCase):
    def test_unchanged(self):
        a = board()
        result = persistent_transition(obs(a), obs(a), obs(a))
        self.assertEqual(result["persistent_changes"], 0)

    def test_persistent_interior_change(self):
        a, b, c = board(), board(), board()
        b[2][2] = [100, 100, 100]
        c[2][2] = [102, 101, 100]
        result = persistent_transition(obs(a), obs(b), obs(c))
        self.assertEqual(result["persistent_interior_changes"], 1)

    def test_transient_change(self):
        a, b, c = board(), board(), board()
        b[2][2] = [100, 100, 100]
        result = persistent_transition(obs(a), obs(b), obs(c))
        self.assertEqual(result["transient_or_unstable_changes"], 1)

    def test_persistent_edge_change(self):
        a, b, c = board(), board(), board()
        b[0][0] = [100, 100, 100]
        c[0][0] = [101, 100, 100]
        result = persistent_transition(obs(a), obs(b), obs(c))
        self.assertEqual(result["persistent_edge_changes"], 1)

    def test_incompatible_calibration_rejected(self):
        a = board()
        other = obs(a)
        other["bounds"] = [2, 1, 99, 99]
        with self.assertRaises(ValueError):
            persistent_transition(obs(a), obs(a), other)

    def test_rejects_boolean_and_out_of_range_rgb(self):
        for sample in ([True, 0, 0], [-1, 0, 0], [256, 0, 0], [1.5, 0, 0]):
            with self.subTest(sample=sample):
                a, b, c = board(), board(), board()
                b[1][1] = sample
                with self.assertRaises(ValueError):
                    persistent_transition(obs(a), obs(b), obs(c))

    def test_rejects_non_finite_thresholds(self):
        a = board()
        for threshold in (float("nan"), float("inf"), True):
            with self.subTest(threshold=threshold):
                with self.assertRaises(ValueError):
                    persistent_transition(
                        obs(a), obs(a), obs(a), threshold=threshold
                    )

    def test_accepts_large_finite_integer_thresholds_without_overflow(self):
        a = board()
        huge = 10 ** 10000
        result = persistent_transition(
            obs(a), obs(a), obs(a),
            threshold=huge, stability=huge,
        )
        self.assertEqual(result["persistent_changes"], 0)

    def test_rejects_extreme_integer_bounds_without_overflow(self):
        a = obs(board())
        a["bounds"] = [1, 1, 10 ** 10000, 99]
        with self.assertRaisesRegex(ValueError, "inside the screenshot"):
            persistent_transition(a, a, a)

    def test_rejects_bounds_outside_source_image(self):
        a = obs(board())
        a["bounds"] = [1, 1, 1080, 100]
        with self.assertRaisesRegex(ValueError, "inside the screenshot"):
            persistent_transition(a, a, a)

    def test_rejects_rgb_grid_that_disagrees_with_calibration(self):
        a = obs(board())
        a["grid_size"] = [4, 5]
        with self.assertRaisesRegex(ValueError, "do not match calibrated"):
            persistent_transition(a, a, a)

    def test_rejects_malformed_grid_dimensions(self):
        a = obs(board())
        a["grid_size"] = [True, 5]
        with self.assertRaises(ValueError):
            persistent_transition(a, a, a)

    def test_safety_flags_remain_false(self):
        a, b, c = board(), board(), board()
        b[2][2] = [100, 100, 100]
        c[2][2] = [100, 100, 100]
        result = persistent_transition(obs(a), obs(b), obs(c))
        self.assertFalse(result["tile_removals_verified"])
        self.assertFalse(result["board_transition_verified"])
        self.assertFalse(result["game_taps_enabled"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
