import json
import tempfile
import unittest
from pathlib import Path

from capture_pipeline import load_capture_config


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
