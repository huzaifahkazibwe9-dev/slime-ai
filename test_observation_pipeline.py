import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from observation_pipeline import evaluate_observations, load_observation


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

            def read_then_replace(path):
                data = real_read_bytes(path)
                reads.append(Path(path).resolve())
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
