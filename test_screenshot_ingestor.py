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
            self.assertGreaterEqual(result["processing_seconds"], 0)
            self.assertEqual(result["sampling_method"], "numpy_vectorized_3x3_median")
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

    def test_identical_screenshot_and_calibration_reuse_exact_board_analysis(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image_path = root / "capture.png"
            baseline_path = root / "baseline.json"
            output_path = root / "observation.json"
            Image.new("RGB", (30, 30), (245, 245, 245)).save(image_path)
            baseline = {"grid_size": [3, 3], "bounds": [3, 3, 27, 27]}
            baseline_path.write_text(json.dumps(baseline))

            ingest(image_path, baseline_path, output_path)
            first = json.loads(output_path.read_text())
            self.assertEqual(first["analysis_cache_status"], "FULL_ANALYSIS")

            from unittest.mock import patch
            with patch("screenshot_ingestor.extract_board",
                       side_effect=AssertionError("duplicate image was re-analysed")):
                ingest(image_path, baseline_path, output_path)

            second = json.loads(output_path.read_text())
            self.assertEqual(second["analysis_cache_status"], "EXACT_MATCH_REUSED")
            self.assertEqual(second["board"], first["board"])
            self.assertEqual(second["source_sha256"], first["source_sha256"])
            self.assertEqual(second["calibration_sha256"], first["calibration_sha256"])
            self.assertFalse(second["gameplay_verified"])
            self.assertFalse(second["game_taps_enabled"])

    def test_incomplete_cached_extraction_forces_full_analysis(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image_path = root / "capture.png"
            baseline_path = root / "baseline.json"
            output_path = root / "observation.json"
            Image.new("RGB", (30, 30), (245, 245, 245)).save(image_path)
            baseline_path.write_text(json.dumps({
                "grid_size": [3, 3], "bounds": [3, 3, 27, 27]
            }))
            ingest(image_path, baseline_path, output_path)
            damaged = json.loads(output_path.read_text())
            damaged.pop("raw_rgb")
            output_path.write_text(json.dumps(damaged))

            ingest(image_path, baseline_path, output_path)
            repaired = json.loads(output_path.read_text())
            self.assertEqual(repaired["analysis_cache_status"], "FULL_ANALYSIS")
            self.assertEqual(len(repaired["raw_rgb"]), 3)

    def test_calibration_change_invalidates_cached_board_analysis(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image_path = root / "capture.png"
            baseline_path = root / "baseline.json"
            output_path = root / "observation.json"
            Image.new("RGB", (30, 30), (245, 245, 245)).save(image_path)
            baseline_path.write_text(json.dumps({
                "grid_size": [3, 3], "bounds": [3, 3, 27, 27]
            }))
            ingest(image_path, baseline_path, output_path)

            baseline_path.write_text(json.dumps({
                "grid_size": [3, 3], "bounds": [4, 4, 26, 26]
            }))
            ingest(image_path, baseline_path, output_path)
            result = json.loads(output_path.read_text())
            self.assertEqual(result["analysis_cache_status"], "FULL_ANALYSIS")
            self.assertEqual(result["bounds"], [4, 4, 26, 26])

    def test_changed_screenshot_invalidates_cached_board_analysis(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image_path = root / "capture.png"
            baseline_path = root / "baseline.json"
            output_path = root / "observation.json"
            Image.new("RGB", (30, 30), (245, 245, 245)).save(image_path)
            baseline_path.write_text(json.dumps({
                "grid_size": [3, 3], "bounds": [3, 3, 27, 27]
            }))
            ingest(image_path, baseline_path, output_path)

            Image.new("RGB", (30, 30), (230, 30, 30)).save(image_path)
            ingest(image_path, baseline_path, output_path)
            result = json.loads(output_path.read_text())
            self.assertEqual(result["analysis_cache_status"], "FULL_ANALYSIS")
            self.assertEqual(set(result["counts"]), {"red"})

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
                captured_at="2026-11-23T12:30:00+03:00",
            )
            result = json.loads(output_path.read_text())
            self.assertEqual(
                result["capture_session_id"], "session-2026-11-23-A"
            )
            self.assertEqual(result["captured_at"], "2026-11-23T12:30:00+03:00")
            self.assertTrue(result["timestamp_identified"])

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

    def test_rejects_non_finite_calibration_bounds(self):
        path = Path("data/test_ingestor_nonfinite.png")
        path.parent.mkdir(exist_ok=True)
        Image.new("RGB", (30, 30)).save(path)
        try:
            for bad_value in (float("nan"), float("inf"), float("-inf"), True):
                with self.subTest(value=bad_value):
                    with self.assertRaises(ValueError):
                        extract_board(path, {
                            "grid_size": [3, 3],
                            "bounds": [3, 3, bad_value, 27],
                        })
        finally:
            path.unlink(missing_ok=True)

    def test_ingest_binds_hash_and_pixels_to_one_immutable_byte_snapshot(self):
        import hashlib
        from io import BytesIO
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image_path = root / "capture.png"
            alternate_path = root / "alternate.png"
            baseline_path = root / "baseline.json"
            output_path = root / "observation.json"

            Image.new("RGB", (30, 30), (245, 245, 245)).save(image_path)
            Image.new("RGB", (30, 30), (230, 30, 30)).save(alternate_path)
            original_bytes = image_path.read_bytes()
            alternate_bytes = alternate_path.read_bytes()
            baseline_path.write_text(json.dumps({
                "grid_size": [3, 3],
                "bounds": [3, 3, 27, 27],
            }))

            from screenshot_ingestor import extract_board as real_extract_board

            def replace_source_then_extract(image_source, calibration):
                self.assertIsInstance(image_source, bytes)
                self.assertEqual(image_source, original_bytes)
                image_path.write_bytes(alternate_bytes)
                return real_extract_board(image_source, calibration)

            with patch(
                "screenshot_ingestor.extract_board",
                side_effect=replace_source_then_extract,
            ):
                ingest(image_path, baseline_path, output_path)

            result = json.loads(output_path.read_text())
            self.assertEqual(
                result["source_sha256"],
                hashlib.sha256(original_bytes).hexdigest(),
            )
            self.assertEqual(result["counts"], {"white": 9})
            self.assertEqual(
                Image.open(BytesIO(original_bytes)).size,
                result["image_size"],
            )
            self.assertNotEqual(image_path.read_bytes(), original_bytes)
            self.assertFalse(result["gameplay_verified"])
            self.assertFalse(result["game_taps_enabled"])

    def test_rejects_malformed_calibration_shapes(self):
        path = Path("data/test_ingestor_bad_calibration.png")
        path.parent.mkdir(exist_ok=True)
        Image.new("RGB", (30, 30)).save(path)
        try:
            for calibration in (
                [], {"grid_size": [3], "bounds": [3, 3, 27, 27]},
                {"grid_size": [3, 3], "bounds": [3, 3, 27]},
            ):
                with self.subTest(calibration=calibration):
                    with self.assertRaises(ValueError):
                        extract_board(path, calibration)
        finally:
            path.unlink(missing_ok=True)

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
