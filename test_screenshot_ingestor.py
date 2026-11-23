import json
import tempfile
import unittest
from pathlib import Path
from PIL import Image

from screenshot_ingestor import classify_rgb, extract_board, ingest


class ScreenshotIngestorTests(unittest.TestCase):
    def test_white_classification(self):
        self.assertEqual(classify_rgb((245, 245, 245)), "white")

    def test_cyan_classification(self):
        self.assertEqual(classify_rgb((104, 195, 233)), "cyan")

    def test_red_classification(self):
        self.assertEqual(classify_rgb((230, 30, 30)), "red")

    def test_extracts_complete_grid(self):
        path = Path("data/test_ingestor_image.png")
        path.parent.mkdir(exist_ok=True)
        Image.new("RGB", (30, 30), (245, 245, 245)).save(path)
        try:
            calibration = {
                "grid_size": [3, 3],
                "bounds": [3, 3, 27, 27],
            }
            result = extract_board(path, calibration)
            self.assertEqual(len(result["board"]), 3)
            self.assertTrue(all(len(row) == 3 for row in result["board"]))
            self.assertEqual(sum(result["counts"].values()), 9)
        finally:
            path.unlink(missing_ok=True)

    def test_rejects_image_too_small(self):
        path = Path("data/test_ingestor_small.png")
        path.parent.mkdir(exist_ok=True)
        Image.new("RGB", (10, 10)).save(path)
        try:
            with self.assertRaises(ValueError):
                extract_board(path, {
                    "grid_size": [3, 3],
                    "bounds": [3, 3, 27, 27],
                })
        finally:
            path.unlink(missing_ok=True)

    def test_rejects_negative_board_bounds(self):
        path = Path("data/test_ingestor_negative.png")
        path.parent.mkdir(exist_ok=True)
        Image.new("RGB", (30, 30)).save(path)
        try:
            with self.assertRaises(ValueError):
                extract_board(path, {
                    "grid_size": [3, 3],
                    "bounds": [-1, 3, 27, 27],
                })
        finally:
            path.unlink(missing_ok=True)

    def test_rejects_zero_grid_dimension(self):
        path = Path("data/test_ingestor_zero_grid.png")
        path.parent.mkdir(exist_ok=True)
        Image.new("RGB", (30, 30)).save(path)
        try:
            with self.assertRaises(ValueError):
                extract_board(path, {
                    "grid_size": [0, 3],
                    "bounds": [3, 3, 27, 27],
                })
        finally:
            path.unlink(missing_ok=True)

    def test_ingest_binds_board_snapshot_to_source_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image_path = root / "capture.png"
            baseline_path = root / "baseline.json"
            output_path = root / "observation.json"
            Image.new("RGB", (30, 30), (245, 245, 245)).save(image_path)
            baseline_path.write_text(json.dumps({
                "grid_size": [3, 3],
                "bounds": [3, 3, 27, 27],
            }))
            ingest(image_path, baseline_path, output_path)
            result = json.loads(output_path.read_text())
            self.assertEqual(
                result["board_snapshot_id"],
                result["snapshot_id"],
            )
            self.assertEqual(
                result["snapshot_id"],
                "sha256:" + result["source_sha256"],
            )
            self.assertFalse(result["gameplay_verified"])
            self.assertFalse(result["game_taps_enabled"])

    def test_ingest_requires_explicit_session_to_bind_capture(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image_path = root / "capture.png"
            baseline_path = root / "baseline.json"
            output_path = root / "observation.json"
            Image.new("RGB", (30, 30), (245, 245, 245)).save(image_path)
            baseline_path.write_text(json.dumps({
                "grid_size": [3, 3],
                "bounds": [3, 3, 27, 27],
            }))
            ingest(
                image_path, baseline_path, output_path,
                capture_session_id="session-2026-11-23-A",
            )
            result = json.loads(output_path.read_text())
            self.assertEqual(
                result["capture_session_id"], "session-2026-11-23-A"
            )

    def test_ingest_rejects_malformed_capture_session_id(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image_path = root / "capture.png"
            baseline_path = root / "baseline.json"
            Image.new("RGB", (30, 30), (245, 245, 245)).save(image_path)
            baseline_path.write_text(json.dumps({
                "grid_size": [3, 3],
                "bounds": [3, 3, 27, 27],
            }))
            with self.assertRaisesRegex(ValueError, "Invalid capture session ID"):
                ingest(
                    image_path, baseline_path, root / "observation.json",
                    capture_session_id="bad session id",
                )

    def test_rejects_bounds_without_sampling_margin(self):
        path = Path("data/test_ingestor_edge_bounds.png")
        path.parent.mkdir(exist_ok=True)
        Image.new("RGB", (30, 30)).save(path)
        try:
            with self.assertRaises(ValueError):
                extract_board(path, {
                    "grid_size": [3, 3],
                    "bounds": [3, 3, 30, 27],
                })
        finally:
            path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
