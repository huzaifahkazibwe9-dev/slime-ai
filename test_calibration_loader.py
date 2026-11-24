"""Regression tests for fail-closed saved calibration loading."""

import json
import tempfile
import unittest
from pathlib import Path

from conveyor_geometry import load_verified_calibration


class VerifiedCalibrationLoaderTests(unittest.TestCase):
    def test_missing_file_has_actionable_error(self):
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "conveyor_calibration.json"
            with self.assertRaisesRegex(FileNotFoundError, "real screenshot"):
                load_verified_calibration(missing)

    def test_invalid_json_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "calibration.json"
            path.write_text("{not json")
            with self.assertRaisesRegex(ValueError, "valid JSON"):
                load_verified_calibration(path)

    def test_non_object_root_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "calibration.json"
            path.write_text(json.dumps([]))
            with self.assertRaisesRegex(ValueError, "JSON object"):
                load_verified_calibration(path)

    def test_unconfirmed_calibration_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "calibration.json"
            path.write_text(json.dumps({"verified_by_user": False}))
            with self.assertRaisesRegex(ValueError, "explicitly confirmed"):
                load_verified_calibration(path)

    def test_confirmed_object_is_loaded(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "calibration.json"
            expected = {"verified_by_user": True, "shooters": []}
            path.write_text(json.dumps(expected))
            self.assertEqual(load_verified_calibration(path), expected)


if __name__ == "__main__":
    unittest.main()
