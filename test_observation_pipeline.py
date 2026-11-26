import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from observation_pipeline import evaluate_observations, load_observation


def observation(board, image_size=(1080, 2220),
                grid_size=None, bounds=(201, 431, 881, 1113)):
    if grid_size is None:
        grid_size = (
            len(board[0]) if board and isinstance(board[0], list) else 0,
            len(board),
        )
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
            observation(
                self.board, image_size=(900, 1400),
                bounds=(201, 231, 881, 1113),
            ),
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

    def test_board_dimensions_must_match_declared_grid_columns(self):
        invalid = observation(self.board, grid_size=(6, 5))
        result = evaluate_observations(invalid, invalid)
        self.assertEqual(result["status"], "REJECTED_INVALID_BOARD")
        self.assertIn("declares 6", result["errors"][0])
        self.assertFalse(result["transition_verified"])
        self.assertFalse(result["tile_removals_verified"])
        self.assertFalse(result["game_taps_enabled"])

    def test_board_dimensions_must_match_declared_grid_rows(self):
        invalid = observation(self.board, grid_size=(5, 6))
        result = evaluate_observations(invalid, invalid)
        self.assertEqual(result["status"], "REJECTED_INVALID_BOARD")
        self.assertIn("declares 6", result["errors"][0])

    def test_boolean_grid_dimensions_are_rejected(self):
        invalid = observation(self.board, grid_size=(True, 5))
        result = evaluate_observations(invalid, invalid)
        self.assertEqual(result["status"], "REJECTED_INVALID_OBSERVATION")
        self.assertIn("positive integers", result["errors"][0])

    def test_non_list_board_rows_are_rejected_against_grid(self):
        invalid = observation(self.board, grid_size=(5, 5))
        invalid["board"] = [tuple(row) for row in self.board]
        result = evaluate_observations(invalid, invalid)
        self.assertEqual(result["status"], "REJECTED_INVALID_BOARD")
        self.assertIn("must be a list", result["errors"][0])

    def test_non_object_observations_are_rejected_safely(self):
        for invalid in (None, [], "board", 7):
            result = evaluate_observations(invalid, observation(self.board))
            self.assertEqual(
                result["status"], "REJECTED_INVALID_OBSERVATION"
            )
            self.assertFalse(result["transition_verified"])
            self.assertFalse(result["tile_removals_verified"])
            self.assertFalse(result["game_taps_enabled"])

    def test_boolean_and_non_positive_image_dimensions_are_rejected(self):
        for image_size in ([True, 2220], [1080, 0], [1080], [1080.0, 2220]):
            invalid = observation(self.board, image_size=image_size)
            result = evaluate_observations(invalid, invalid)
            self.assertEqual(
                result["status"], "REJECTED_INVALID_OBSERVATION"
            )
            self.assertIn("image_size", result["errors"][0])

    def test_sampling_bounds_must_be_finite_and_inside_image(self):
        for bounds in (
            [201, 431, 1080, 1113],
            [201, 431, 800, 2220],
            [float("nan"), 431, 881, 1113],
            [201, 431, 881],
        ):
            invalid = observation(self.board, bounds=bounds)
            result = evaluate_observations(invalid, invalid)
            self.assertEqual(
                result["status"], "REJECTED_INVALID_OBSERVATION"
            )
            self.assertIn("bounds", result["errors"][0])

    def test_sampling_bounds_must_produce_non_overlapping_3x3_windows(self):
        invalid = observation(
            self.board,
            bounds=(201, 431, 205, 435),
        )
        result = evaluate_observations(invalid, invalid)
        self.assertEqual(
            result["status"], "REJECTED_INVALID_OBSERVATION"
        )
        self.assertIn("overlapping 3x3", result["errors"][0])
        self.assertFalse(result["transition_verified"])
        self.assertFalse(result["tile_removals_verified"])
        self.assertFalse(result["game_taps_enabled"])

    def test_rounded_sample_centres_must_leave_room_inside_image(self):
        cases = (
            (
                [["white"]],
                (1078.6, 431, 1079, 1113),
            ),
            (
                [["white"]],
                (201, 2218.6, 881, 2219),
            ),
        )
        for board, bounds in cases:
            with self.subTest(bounds=bounds):
                invalid = observation(
                    board,
                    grid_size=(1, 1),
                    bounds=bounds,
                )
                result = evaluate_observations(invalid, invalid)
                self.assertEqual(
                    result["status"], "REJECTED_INVALID_OBSERVATION"
                )
                self.assertIn("outside image_size", result["errors"][0])
                self.assertFalse(result["transition_verified"])
                self.assertFalse(result["tile_removals_verified"])
                self.assertFalse(result["game_taps_enabled"])

    def test_unknown_colour_labels_are_rejected(self):
        invalid_board = [row[:] for row in self.board]
        invalid_board[1][2] = "transparent"
        invalid = observation(invalid_board)
        result = evaluate_observations(invalid, invalid)
        self.assertEqual(result["status"], "REJECTED_INVALID_BOARD")
        self.assertIn("unknown colour label", result["errors"][0])
        self.assertFalse(result["transition_verified"])
        self.assertFalse(result["tile_removals_verified"])
        self.assertFalse(result["game_taps_enabled"])

    def test_non_string_colour_labels_are_rejected(self):
        invalid_board = [row[:] for row in self.board]
        invalid_board[1][2] = None
        invalid = observation(invalid_board)
        result = evaluate_observations(invalid, invalid)
        self.assertEqual(result["status"], "REJECTED_INVALID_BOARD")
        self.assertIn("unknown colour label", result["errors"][0])

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
            observation(
                self.board, image_size=(900, 1400),
                bounds=(201, 231, 881, 1113),
            ),
        )
        self.assertFalse(result["transition_verified"])
        self.assertFalse(result["tile_removals_verified"])
        self.assertFalse(result["game_taps_enabled"])


    def test_load_observation_hash_and_pixels_use_one_immutable_byte_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image_path = root / "capture.png"
            calibration = {
                "grid_size": [3, 3],
                "bounds": [3, 3, 27, 27],
            }
            Image.new("RGB", (30, 30), (245, 245, 245)).save(image_path)
            original_bytes = image_path.read_bytes()
            real_read_bytes = Path.read_bytes
            reads = []

            def read_then_replace(*_args, **_kwargs):
                data = real_read_bytes(image_path)
                reads.append(image_path.resolve())
                Image.new("RGB", (30, 30), (230, 30, 30)).save(image_path)
                return data

            with patch("pathlib.Path.read_bytes", side_effect=read_then_replace):
                result = load_observation(image_path, calibration)

            self.assertEqual(reads, [image_path.resolve()])
            self.assertEqual(
                result["sha256"], hashlib.sha256(original_bytes).hexdigest()
            )
            self.assertEqual(result["board"][0][0], "white")
            self.assertEqual(result["raw_rgb"][0][0], [245, 245, 245])
            self.assertNotEqual(image_path.read_bytes(), original_bytes)


if __name__ == "__main__":
    unittest.main(verbosity=2)
