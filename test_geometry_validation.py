import copy
import unittest

from geometry_validation import validate_calibration


def _base_calibration():
    """Minimal synthetic calibration that passes all checks against EXPECTED."""
    return {
        "verified_by_user": True,
        "image_size": [1080, 2220],
        "board_grid": [35, 35],
        "directions": {
            "bottom": "up",
            "right": "left",
            "top": "down",
            "left": "right",
        },
        "shooters": [
            {"id": "bottom_1", "segment": "bottom", "center": [400, 1500]},
            {"id": "bottom_2", "segment": "bottom", "center": [535, 1500]},
            {"id": "right_1", "segment": "right", "center": [1000, 665]},
            {"id": "right_2", "segment": "right", "center": [1000, 805]},
            {"id": "top_1", "segment": "top", "center": [730, 300]},
            {"id": "top_2", "segment": "top", "center": [845, 300]},
            {"id": "left_1", "segment": "left", "center": [100, 470]},
            {"id": "left_2", "segment": "left", "center": [100, 610]},
        ],
    }


class GeometryValidationTests(unittest.TestCase):
    def test_valid_synthetic_calibration_passes(self):
        data = _base_calibration()
        report = validate_calibration(data)
        self.assertEqual(report["shooters_checked"], 8)
        self.assertTrue(report["all_coordinate_checks_passed"])
        self.assertFalse(report["actual_firing_verified"])
        self.assertFalse(report["gameplay_access_enabled"])
        self.assertEqual(len(report["results"]), 8)
        for item in report["results"]:
            self.assertFalse(item["actual_firing_verified"])
            self.assertFalse(item["gameplay_access_enabled"])
            self.assertTrue(item["screen_position_verified"])

    def test_unconfirmed_calibration_rejected(self):
        data = _base_calibration()
        data["verified_by_user"] = False
        with self.assertRaises(ValueError) as ctx:
            validate_calibration(data)
        self.assertIn("not user-confirmed", str(ctx.exception))

    def test_missing_verified_flag_rejected(self):
        data = _base_calibration()
        del data["verified_by_user"]
        with self.assertRaises(ValueError) as ctx:
            validate_calibration(data)
        self.assertIn("not user-confirmed", str(ctx.exception))

    def test_invalid_image_dimensions_rejected(self):
        data = _base_calibration()
        data["image_size"] = [0, 2220]
        with self.assertRaises(ValueError) as ctx:
            validate_calibration(data)
        self.assertIn("Invalid image or board dimensions", str(ctx.exception))

    def test_invalid_board_grid_rejected(self):
        data = _base_calibration()
        data["board_grid"] = [35, -1]
        with self.assertRaises(ValueError) as ctx:
            validate_calibration(data)
        self.assertIn("Invalid image or board dimensions", str(ctx.exception))

    def test_duplicate_shooter_ids_rejected(self):
        data = _base_calibration()
        data["shooters"][1]["id"] = "bottom_1"
        with self.assertRaises(ValueError) as ctx:
            validate_calibration(data)
        self.assertIn("Duplicate shooter IDs", str(ctx.exception))

    def test_wrong_shooter_id_set_rejected(self):
        data = _base_calibration()
        data["shooters"][0]["id"] = "bottom_99"
        with self.assertRaises(ValueError) as ctx:
            validate_calibration(data)
        self.assertIn("do not match expected calibration", str(ctx.exception))

    def test_centre_outside_screenshot_rejected(self):
        data = _base_calibration()
        data["shooters"][0]["center"] = [2000, 1500]
        with self.assertRaises(ValueError) as ctx:
            validate_calibration(data)
        self.assertIn("centre outside screenshot", str(ctx.exception))

    def test_direction_mapping_mismatch_rejected(self):
        data = _base_calibration()
        data["directions"]["bottom"] = "down"
        with self.assertRaises(ValueError) as ctx:
            validate_calibration(data)
        self.assertIn("direction mapping mismatch", str(ctx.exception))

    def test_unexpected_lane_rejected(self):
        data = copy.deepcopy(_base_calibration())
        # Move bottom_1 far enough that its calculated lane no longer matches EXPECTED
        data["shooters"][0]["center"] = [200, 1500]
        with self.assertRaises(ValueError) as ctx:
            validate_calibration(data)
        self.assertIn("unexpected calculated lane", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
