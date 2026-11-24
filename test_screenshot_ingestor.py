import json
import tempfile
import unittest

import numpy as np
from pathlib import Path
from PIL import Image

from screenshot_ingestor import (
    classify_rgb, extract_board, ingest, sample_variation_diagnostics,
)


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

    def test_non_square_grid_has_matching_diagnostic_dimensions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "non_square.png"
            Image.new("RGB", (30, 30), (245, 245, 245)).save(path)

            result = extract_board(path, {
                "grid_size": [3, 2],
                "bounds": [3, 3, 27, 15],
            })

        self.assertEqual(result["grid_size"], [3, 2])
        self.assertEqual(len(result["board"]), 2)
        self.assertTrue(all(len(row) == 3 for row in result["board"]))
        self.assertEqual(len(result["raw_rgb"]), 2)
        self.assertEqual(len(result["sample_diagnostics"]), 2)
        self.assertTrue(all(
            len(row) == 3 for row in result["sample_diagnostics"]
        ))

    def test_sample_variation_is_informational_and_preserves_median(self):
        uniform = np.full((3, 3, 3), 245, dtype=np.uint8)
        varied_values = [0, 0, 0, 245, 245, 245, 245, 255, 255]
        varied = np.asarray(varied_values, dtype=np.uint8).reshape(3, 3, 1)
        varied = np.repeat(varied, 3, axis=2)

        uniform_diagnostic = sample_variation_diagnostics(uniform)
        varied_diagnostic = sample_variation_diagnostics(varied)

        self.assertEqual(uniform_diagnostic["channel_median_absolute_deviation"], [0.0] * 3)
        self.assertEqual(varied_diagnostic["channel_median_absolute_deviation"], [10.0] * 3)
        self.assertEqual(uniform_diagnostic["status"], "UNASSESSED")
        self.assertEqual(varied_diagnostic["status"], "UNASSESSED")
        self.assertEqual(tuple(np.median(uniform, axis=(0, 1))), (245.0,) * 3)
        self.assertEqual(tuple(np.median(varied, axis=(0, 1))), (245.0,) * 3)
        self.assertEqual(classify_rgb(tuple(np.median(uniform, axis=(0, 1)))), "white")
        self.assertEqual(classify_rgb(tuple(np.median(varied, axis=(0, 1)))), "white")

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

    def test_missing_or_malformed_cached_sample_diagnostics_forces_full_analysis(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image_path = root / "capture.png"
            baseline_path = root / "baseline.json"
            output_path = root / "observation.json"
            Image.new("RGB", (30, 30), (245, 245, 245)).save(image_path)
            baseline_path.write_text(json.dumps({
                "grid_size": [3, 3], "bounds": [3, 3, 27, 27]
            }))

            for damage in ("missing", "wrong_dimensions", "invalid_value"):
                with self.subTest(damage=damage):
                    ingest(image_path, baseline_path, output_path)
                    cached = json.loads(output_path.read_text())
                    if damage == "missing":
                        cached.pop("sample_diagnostics")
                    elif damage == "wrong_dimensions":
                        cached["sample_diagnostics"].pop()
                    else:
                        cached["sample_diagnostics"][0][0][
                            "channel_median_absolute_deviation"
                        ][0] = 256
                    output_path.write_text(json.dumps(cached))

                    ingest(image_path, baseline_path, output_path)
                    repaired = json.loads(output_path.read_text())
                    self.assertEqual(
                        repaired["analysis_cache_status"], "FULL_ANALYSIS"
                    )
                    self.assertEqual(len(repaired["sample_diagnostics"]), 3)
                    self.assertTrue(all(
                        len(row) == 3
                        for row in repaired["sample_diagnostics"]
                    ))

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
