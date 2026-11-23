import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from capture_pipeline import load_capture_config, run_capture_pipeline


class CapturePipelineConfigTests(unittest.TestCase):
    def write_config(self, root, value):
        path = Path(root) / "capture.json"
        path.write_text(json.dumps(value))
        return path

    def test_accepts_explicit_same_capture_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_config(directory, {
                "panel_bounds": [10, 20, 900, 600],
                "capture_session_id": "session-abc",
                "captured_at": "2026-11-23T12:30:00+03:00",
            })
            result = load_capture_config(path)
        self.assertEqual(result["panel_bounds"], [10, 20, 900, 600])
        self.assertEqual(result["capture_session_id"], "session-abc")
        self.assertEqual(result["captured_at"], "2026-11-23T12:30:00+03:00")

    def test_rejects_missing_session_id(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_config(directory, {
                "panel_bounds": [10, 20, 900, 600],
                "captured_at": "2026-11-23T12:30:00+03:00",
            })
            with self.assertRaisesRegex(ValueError, "session_id"):
                load_capture_config(path)

    def test_rejects_timestamp_without_utc_offset(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_config(directory, {
                "panel_bounds": [10, 20, 900, 600],
                "capture_session_id": "session-abc",
                "captured_at": "2026-11-23T12:30:00",
            })
            with self.assertRaisesRegex(ValueError, "UTC offset"):
                load_capture_config(path)

    def test_runs_ingestor_and_detector_with_identical_capture_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            screenshot = root / "source.jpg"
            screenshot.write_bytes(b"placeholder")
            config = self.write_config(directory, {
                "panel_bounds": [10, 20, 900, 600],
                "capture_session_id": "session-abc",
                "captured_at": "2026-11-23T12:30:00+03:00",
            })
            with patch("capture_pipeline.subprocess.run") as run:
                run_capture_pipeline(screenshot, config)
        self.assertEqual(run.call_count, 2)
        ingestor_args = run.call_args_list[0].args[0]
        detector_args = run.call_args_list[1].args[0]
        for flag in ("--capture-session-id", "session-abc",
                     "--captured-at", "2026-11-23T12:30:00+03:00"):
            self.assertIn(flag, ingestor_args)
            self.assertIn(flag, detector_args)
        self.assertIn("--extract-panel", detector_args)
        self.assertEqual(
            detector_args[detector_args.index("--panel-bounds") + 1:
                          detector_args.index("--panel-bounds") + 5],
            ["10", "20", "900", "600"],
        )

    def test_rejects_non_integer_crop_bounds(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_config(directory, {
                "panel_bounds": [10, 20, "900", 600],
                "capture_session_id": "session-abc",
                "captured_at": "2026-11-23T12:30:00+03:00",
            })
            with self.assertRaisesRegex(ValueError, "integer coordinates"):
                load_capture_config(path)


if __name__ == "__main__":
    unittest.main()
