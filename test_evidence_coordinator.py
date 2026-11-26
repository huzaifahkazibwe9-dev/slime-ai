import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image

from evidence_coordinator import audit_transition, coordinate, OBSERVATION, REPORT


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

    def test_coordinate_binds_extraction_and_hash_to_one_byte_snapshot(self):
        """Extraction, hash and EXIF must come from the same immutable bytes.

        Even if the source path is replaced after the initial read, the
        returned digest and board must still match the original snapshot.
        """
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image_path = root / "capture.png"
            baseline_path = root / "baseline.json"

            # Solid white image that classifies as all-"white"
            Image.new("RGB", (30, 30), (245, 245, 245)).save(image_path)
            original_bytes = image_path.read_bytes()
            expected_digest = hashlib.sha256(original_bytes).hexdigest()

            board = [["white"] * 3 for _ in range(3)]
            baseline_path.write_text(json.dumps({
                "grid_size": [3, 3],
                "bounds": [3, 3, 27, 27],
                "board": board,
            }))

            def replace_source_then_extract(path, calibration):
                # Simulate a race: replace the original path after the
                # snapshot has been taken but before extraction finishes.
                Image.new("RGB", (30, 30), (230, 30, 30)).save(image_path)
                from screenshot_ingestor import extract_board as real_extract
                return real_extract(path, calibration)

            with patch(
                "evidence_coordinator.extract_board",
                side_effect=replace_source_then_extract,
            ):
                result = coordinate(
                    image_path,
                    baseline_path=baseline_path,
                )

            self.assertEqual(result["source_sha256"], expected_digest)
            self.assertEqual(result["snapshot_id"], "sha256:" + expected_digest)
            self.assertFalse(result["game_taps_enabled"])
            self.assertFalse(result["gameplay_verified"])

            # The observation written from the snapshot must also match
            observation = json.loads(OBSERVATION.read_text())
            self.assertEqual(observation["source_sha256"], expected_digest)
            self.assertEqual(observation["board"], board)
            self.assertEqual(result["transition"]["status"], "UNCHANGED")

            # Clean up the fixed-path artefacts the coordinator writes
            OBSERVATION.unlink(missing_ok=True)
            REPORT.unlink(missing_ok=True)

    def test_coordinate_does_not_write_artefacts_on_extraction_failure(self):
        """If extraction raises, no observation or report files must be left behind.

        Fail-closed: partial evidence must never be promoted.
        """
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image_path = root / "capture.png"
            baseline_path = root / "baseline.json"

            Image.new("RGB", (30, 30), (245, 245, 245)).save(image_path)
            board = [["white"] * 3 for _ in range(3)]
            baseline_path.write_text(json.dumps({
                "grid_size": [3, 3],
                "bounds": [3, 3, 27, 27],
                "board": board,
            }))

            # Ensure clean slate
            OBSERVATION.unlink(missing_ok=True)
            REPORT.unlink(missing_ok=True)

            with patch(
                "evidence_coordinator.extract_board",
                side_effect=ValueError("simulated extraction failure"),
            ):
                with self.assertRaises(ValueError):
                    coordinate(image_path, baseline_path=baseline_path)

            self.assertFalse(OBSERVATION.exists())
            self.assertFalse(REPORT.exists())

    def test_coordinate_rejects_grid_size_mismatch(self):
        """Extracted grid must match baseline; mismatch must raise and leave no artefacts."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image_path = root / "capture.png"
            baseline_path = root / "baseline.json"

            Image.new("RGB", (30, 30), (245, 245, 245)).save(image_path)
            board = [["white"] * 3 for _ in range(3)]
            baseline_path.write_text(json.dumps({
                "grid_size": [4, 4],  # mismatch
                "bounds": [3, 3, 27, 27],
                "board": board,
            }))

            OBSERVATION.unlink(missing_ok=True)
            REPORT.unlink(missing_ok=True)

            mismatched = {
                "grid_size": [3, 3],
                "bounds": [3, 3, 27, 27],
                "board": board,
                "counts": {},
                "raw_rgb": [],
            }
            with patch(
                "evidence_coordinator.extract_board",
                return_value=mismatched,
            ):
                with self.assertRaises(ValueError) as ctx:
                    coordinate(image_path, baseline_path=baseline_path)
                self.assertIn("grid does not match", str(ctx.exception).lower())

            self.assertFalse(OBSERVATION.exists())
            self.assertFalse(REPORT.exists())


    def test_coordinate_rejects_missing_baseline_without_artefacts(self):
        """Missing baseline must raise before any artefact is written."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image_path = root / "capture.png"
            Image.new("RGB", (30, 30), (245, 245, 245)).save(image_path)
            missing_baseline = root / "does_not_exist.json"

            OBSERVATION.unlink(missing_ok=True)
            REPORT.unlink(missing_ok=True)

            with self.assertRaises(FileNotFoundError):
                coordinate(image_path, baseline_path=missing_baseline)

            self.assertFalse(OBSERVATION.exists())
            self.assertFalse(REPORT.exists())

    def test_coordinate_rejects_invalid_baseline_json_without_artefacts(self):
        """Malformed baseline JSON must raise and leave no observation/report files."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image_path = root / "capture.png"
            baseline_path = root / "baseline.json"
            Image.new("RGB", (30, 30), (245, 245, 245)).save(image_path)
            baseline_path.write_text("{ not valid json")

            OBSERVATION.unlink(missing_ok=True)
            REPORT.unlink(missing_ok=True)

            with self.assertRaises(json.JSONDecodeError):
                coordinate(image_path, baseline_path=baseline_path)

            self.assertFalse(OBSERVATION.exists())
            self.assertFalse(REPORT.exists())

    def test_coordinate_rejects_bounds_mismatch_without_artefacts(self):
        """Calibration bounds mismatch must raise and leave no artefacts."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image_path = root / "capture.png"
            baseline_path = root / "baseline.json"

            Image.new("RGB", (30, 30), (245, 245, 245)).save(image_path)
            board = [["white"] * 3 for _ in range(3)]
            baseline_path.write_text(json.dumps({
                "grid_size": [3, 3],
                "bounds": [3, 3, 27, 27],
                "board": board,
            }))

            OBSERVATION.unlink(missing_ok=True)
            REPORT.unlink(missing_ok=True)

            mismatched = {
                "grid_size": [3, 3],
                "bounds": [0, 0, 30, 30],  # mismatch
                "board": board,
                "counts": {},
                "raw_rgb": [],
            }
            with patch(
                "evidence_coordinator.extract_board",
                return_value=mismatched,
            ):
                with self.assertRaises(ValueError) as ctx:
                    coordinate(image_path, baseline_path=baseline_path)
                self.assertIn("calibration does not match", str(ctx.exception).lower())

            self.assertFalse(OBSERVATION.exists())
            self.assertFalse(REPORT.exists())

if __name__ == "__main__":
    unittest.main()
