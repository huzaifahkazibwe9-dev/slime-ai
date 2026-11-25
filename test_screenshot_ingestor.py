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

    def test_ingest_uses_one_immutable_screenshot_byte_snapshot(self):
        from unittest.mock import patch
        import hashlib

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image_path = root / "capture.png"
            baseline_path = root / "baseline.json"
            output_path = root / "observation.json"
            Image.new("RGB", (30, 30), (245, 245, 245)).save(image_path)
            original_bytes = image_path.read_bytes()
            baseline_path.write_text(json.dumps({
                "grid_size": [3, 3], "bounds": [3, 3, 27, 27]
            }))
            real_read_bytes = Path.read_bytes
            image_reads = []

            def replace_image_after_read():
                data = real_read_bytes(image_path)
                image_reads.append(image_path)
                Image.new("RGB", (30, 30), (230, 30, 30)).save(image_path)
                return data

            with patch("pathlib.Path.read_bytes", side_effect=replace_image_after_read):
                ingest(image_path, baseline_path, output_path)

            result = json.loads(output_path.read_text())
            self.assertEqual(image_reads, [image_path])
            self.assertEqual(
                result["source_sha256"], hashlib.sha256(original_bytes).hexdigest()
            )
            self.assertEqual(result["board"][0][0], "white")
            self.assertEqual(result["raw_rgb"][0][0], [245, 245, 245])
            self.assertEqual(set(result["counts"]), {"white"})
            self.assertFalse(result["gameplay_verified"])
            self.assertFalse(result["game_taps_enabled"])

    def test_cached_pixel_edit_forces_fresh_full_analysis(self):
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
            cached = json.loads(output_path.read_text())
            cached["raw_rgb"][0][0] = [230, 30, 30]
            output_path.write_text(json.dumps(cached))

            ingest(image_path, baseline_path, output_path)
            repaired = json.loads(output_path.read_text())
            self.assertEqual(repaired["analysis_cache_status"], "FULL_ANALYSIS")
            self.assertEqual(repaired["raw_rgb"][0][0], [245, 245, 245])
            self.assertEqual(repaired["board"][0][0], "white")
            self.assertFalse(repaired["gameplay_verified"])
            self.assertFalse(repaired["game_taps_enabled"])

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

    def test_rejects_grid_with_overlapping_sample_windows(self):
        path = Path("data/test_ingestor_dense_grid.png")
        path.parent.mkdir(exist_ok=True)
        Image.new("RGB", (30, 30)).save(path)
        try:
            with self.assertRaisesRegex(ValueError, "overlapping 3x3 sample windows"):
                extract_board(path, {
                    "grid_size": [10, 10],
                    "bounds": [3, 3, 27, 27],
                })
        finally:
            path.unlink(missing_ok=True)

    def test_rejects_grid_dimensions_above_safe_sampling_limit(self):
        path = Path("data/test_ingestor_huge_grid.png")
        path.parent.mkdir(exist_ok=True)
        Image.new("RGB", (30, 30)).save(path)
        try:
            with self.assertRaisesRegex(ValueError, "safe sampling limit"):
                extract_board(path, {
                    "grid_size": [10001, 1],
                    "bounds": [3, 3, 27, 27],
                })
        finally:
            path.unlink(missing_ok=True)
    def test_extraction_records_exact_sample_centres(self):
        path = Path("data/test_ingestor_sample_centres.png")
        path.parent.mkdir(exist_ok=True)
        Image.new("RGB", (30, 30), (245, 245, 245)).save(path)
        try:
            result = extract_board(path, {
                "grid_size": [3, 3], "bounds": [3, 3, 27, 27]
            })
            self.assertEqual(result["sample_centres"], {
                "x": [7, 15, 23], "y": [7, 15, 23]
            })
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


    def test_ingest_rejects_duplicate_calibration_json_keys(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline = root / "baseline.json"
            baseline.write_text(
                '{"grid_size":[2,2],"grid_size":[3,3],"bounds":[3,3,27,27]}'
            )
            with self.assertRaisesRegex(ValueError, "Duplicate JSON object key"):
                ingest(root / "source.png", baseline, root / "output.json")


if __name__ == "__main__":
    unittest.main(verbosity=2)
