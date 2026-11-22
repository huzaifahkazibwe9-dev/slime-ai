import unittest
from persistent_transition import persistent_transition


def obs(board):
    return {
        "image_size": [1080, 2220],
        "grid_size": [5, 5],
        "bounds": [0, 0, 100, 100],
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
        other["bounds"] = [1, 1, 99, 99]
        with self.assertRaises(ValueError):
            persistent_transition(obs(a), obs(a), other)

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
