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
            expected = {
                "verified_by_user": True,
                "image_size": [1080, 2220],
                "board_grid": [35, 35],
                "directions": {
                    "bottom": "up", "right": "left",
                    "top": "down", "left": "right",
                },
                "shooters": [
                    {"id": "bottom_1", "segment": "bottom", "center": [300, 1000]}
                ],
            }
            path.write_text(json.dumps(expected))
            self.assertEqual(load_verified_calibration(path), expected)


    def test_rejects_missing_required_schema(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "calibration.json"
            path.write_text(json.dumps({"verified_by_user": True}))
            with self.assertRaisesRegex(ValueError, "image_size"):
                load_verified_calibration(path)

    def test_rejects_invalid_dimensions_and_duplicate_shooters(self):
        base = {
            "verified_by_user": True,
            "image_size": [1080, 2220],
            "board_grid": [35, 35],
            "directions": {
                "bottom": "up", "right": "left",
                "top": "down", "left": "right",
            },
            "shooters": [
                {"id": "s1", "segment": "bottom", "center": [300, 1000]}
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "calibration.json"
            invalid = dict(base, image_size=[True, 2220])
            path.write_text(json.dumps(invalid))
            with self.assertRaisesRegex(ValueError, "image_size"):
                load_verified_calibration(path)
            duplicate = dict(base, shooters=base["shooters"] * 2)
            path.write_text(json.dumps(duplicate))
            with self.assertRaisesRegex(ValueError, "duplicate ID"):
                load_verified_calibration(path)

    def test_rejects_out_of_image_or_nonfinite_center(self):
        base = {
            "verified_by_user": True,
            "image_size": [1080, 2220],
            "board_grid": [35, 35],
            "directions": {
                "bottom": "up", "right": "left",
                "top": "down", "left": "right",
            },
            "shooters": [
                {"id": "s1", "segment": "bottom", "center": [1080, 1000]}
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "calibration.json"
            path.write_text(json.dumps(base))
            with self.assertRaisesRegex(ValueError, "outside the image"):
                load_verified_calibration(path)


if __name__ == "__main__":
    unittest.main()
