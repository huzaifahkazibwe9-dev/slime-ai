import unittest

from screenshot_ingestor import _cached_board_is_valid, _extraction_payload_sha256


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
        self.cached["extraction_sha256"] = _extraction_payload_sha256(self.cached)

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

    def test_rejects_missing_extraction_payload_digest(self):
        self.cached.pop("extraction_sha256")
        self.assertFalse(self.is_valid())

    def test_rejects_accidental_cached_rgb_payload_edit(self):
        self.cached["raw_rgb"][0][0][0] = 229
        self.assertFalse(self.is_valid())

    def test_rejects_accidental_cached_board_payload_edit(self):
        self.cached["board"][0][0] = "blue"
        self.assertFalse(self.is_valid())

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

    def test_rejects_boolean_colour_count(self):
        self.cached["counts"] = {"red": True}
        self.assertFalse(self.is_valid())

    def test_rejects_noncanonical_zero_count_key(self):
        self.cached["counts"] = {"red": 1, "ultraviolet": 0}
        self.assertFalse(self.is_valid())

    def test_rejects_label_that_disagrees_with_cached_rgb(self):
        self.cached["board"] = [["blue"]]
        self.cached["counts"] = {"blue": 1}
        self.assertFalse(self.is_valid())

    def test_accepts_label_recomputed_from_cached_rgb(self):
        self.cached["board"] = [["red"]]
        self.cached["raw_rgb"] = [[[230, 30, 30]]]
        self.assertTrue(self.is_valid())

    def test_rejects_boolean_cached_grid_dimension(self):
        self.cached["grid_size"] = [True, 1]
        self.assertFalse(self.is_valid())

    def test_rejects_boolean_cached_geometry_coordinate(self):
        self.cached["bounds"] = [True, 1, 99, 99]
        self.assertFalse(self.is_valid())

    def test_rejects_malformed_cached_image_dimensions(self):
        self.cached["image_size"] = [100]
        self.assertFalse(self.is_valid())

    def test_rejects_extremely_large_integer_geometry_without_overflow(self):
        huge = 10 ** 10000
        self.calibration["bounds"] = [huge, 1, 99, 99]
        self.cached["bounds"] = [huge, 1, 99, 99]
        self.assertFalse(self.is_valid())

    def test_rejects_non_finite_cached_geometry(self):
        self.calibration["bounds"] = [1, 1, float("inf"), 99]
        self.cached["bounds"] = [1, 1, float("inf"), 99]
        self.assertFalse(self.is_valid())


if __name__ == "__main__":
    unittest.main(verbosity=2)
