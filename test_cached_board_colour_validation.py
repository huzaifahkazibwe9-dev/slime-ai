import unittest

from screenshot_ingestor import _cached_board_is_valid


class CachedBoardColourValidationTests(unittest.TestCase):
    def setUp(self):
        self.calibration = {
            "grid_size": [1, 1],
            "bounds": [1, 1, 99, 99],
        }
        self.cached = {
            "source_sha256": "source-digest",
            "calibration_sha256": "calibration-digest",
            "image_size": [100, 100],
            "grid_size": [1, 1],
            "bounds": [1, 1, 99, 99],
            "board": [["red"]],
            "raw_rgb": [[[230, 30, 30]]],
            "counts": {"red": 1},
            "sampling_method": "numpy_vectorized_3x3_median",
        }

    def is_valid(self):
        return _cached_board_is_valid(
            self.cached,
            "source-digest",
            "calibration-digest",
            (100, 100),
            self.calibration,
        )

    def test_accepts_well_formed_canonical_cached_board(self):
        self.assertTrue(self.is_valid())

    def test_rejects_unknown_cached_colour_even_when_counts_match(self):
        self.cached["board"] = [["ultraviolet"]]
        self.cached["counts"] = {"ultraviolet": 1}
        self.assertFalse(self.is_valid())

    def test_rejects_non_string_cached_colour(self):
        self.cached["board"] = [[None]]
        self.cached["counts"] = {None: 1}
        self.assertFalse(self.is_valid())

    def test_rejects_cached_colour_count_mismatch(self):
        self.cached["counts"] = {"red": 2}
        self.assertFalse(self.is_valid())


if __name__ == "__main__":
    unittest.main(verbosity=2)
