"""Unit tests for firing_observation.validate_observation.

Pure offline checks against the calibrated EXPECTED geometry.
Does not require device data or interactive input.
"""

import unittest

from firing_observation import validate_observation, EXPECTED


class FiringObservationValidationTests(unittest.TestCase):
    def test_valid_bottom_observation_accepted(self):
        ok, msg = validate_observation(
            "bottom_1", "up", [10, 20], 40, 39, True
        )
        self.assertTrue(ok)
        self.assertIn("consistent", msg.lower())

    def test_valid_top_observation_accepted(self):
        ok, _ = validate_observation(
            "top_1", "down", [27, 5], 10, 9, True
        )
        self.assertTrue(ok)

    def test_valid_left_observation_accepted(self):
        ok, _ = validate_observation(
            "left_1", "right", [3, 2], 5, 4, True
        )
        self.assertTrue(ok)

    def test_valid_right_observation_accepted(self):
        ok, _ = validate_observation(
            "right_1", "left", [30, 12], 8, 7, True
        )
        self.assertTrue(ok)

    def test_unknown_position_rejected(self):
        ok, msg = validate_observation(
            "middle_99", "up", [10, 20], 40, 39, True
        )
        self.assertFalse(ok)
        self.assertIn("Unknown", msg)

    def test_unconfirmed_observation_rejected(self):
        ok, msg = validate_observation(
            "bottom_1", "up", [10, 20], 40, 39, False
        )
        self.assertFalse(ok)
        self.assertIn("not confirmed", msg)

    def test_unconfirmed_none_rejected(self):
        ok, msg = validate_observation(
            "bottom_1", "up", [10, 20], 40, 39, None
        )
        self.assertFalse(ok)

    def test_unconfirmed_string_yes_rejected(self):
        # Strict boolean True required
        ok, _ = validate_observation(
            "bottom_1", "up", [10, 20], 40, 39, "yes"
        )
        self.assertFalse(ok)

    def test_wrong_direction_rejected(self):
        ok, msg = validate_observation(
            "bottom_1", "down", [10, 20], 40, 39, True
        )
        self.assertFalse(ok)
        self.assertIn("direction", msg.lower())

    def test_invalid_direction_string_rejected(self):
        ok, msg = validate_observation(
            "bottom_1", "north", [10, 20], 40, 39, True
        )
        self.assertFalse(ok)
        self.assertIn("Invalid", msg)

    def test_wrong_lane_rejected(self):
        ok, msg = validate_observation(
            "bottom_1", "up", [11, 20], 40, 39, True
        )
        self.assertFalse(ok)
        self.assertIn("lane", msg.lower())

    def test_cell_outside_board_rejected(self):
        ok, msg = validate_observation(
            "top_1", "down", [27, 35], 40, 39, True
        )
        self.assertFalse(ok)
        self.assertIn("outside", msg.lower())

    def test_negative_cell_coordinate_rejected(self):
        ok, msg = validate_observation(
            "bottom_1", "up", [-1, 20], 40, 39, True
        )
        self.assertFalse(ok)

    def test_non_integer_cell_rejected(self):
        ok, msg = validate_observation(
            "bottom_1", "up", [10.5, 20], 40, 39, True
        )
        self.assertFalse(ok)
        self.assertIn("integer", msg.lower())

    def test_boolean_cell_coordinate_rejected(self):
        # bool is a subclass of int; must be rejected explicitly
        ok, msg = validate_observation(
            "bottom_1", "up", [True, 20], 40, 39, True
        )
        self.assertFalse(ok)
        self.assertIn("integer", msg.lower())

    def test_cell_wrong_length_rejected(self):
        ok, msg = validate_observation(
            "bottom_1", "up", [10], 40, 39, True
        )
        self.assertFalse(ok)
        self.assertIn("[x, y]", msg)

    def test_ammo_no_decrease_rejected(self):
        ok, msg = validate_observation(
            "bottom_1", "up", [10, 20], 40, 40, True
        )
        self.assertFalse(ok)
        self.assertIn("Ammo", msg)

    def test_ammo_increase_rejected(self):
        ok, msg = validate_observation(
            "bottom_1", "up", [10, 20], 40, 41, True
        )
        self.assertFalse(ok)

    def test_ammo_before_zero_or_negative_rejected(self):
        ok, msg = validate_observation(
            "bottom_1", "up", [10, 20], 0, -1, True
        )
        self.assertFalse(ok)

    def test_negative_ammo_after_rejected(self):
        ok, msg = validate_observation(
            "bottom_1", "up", [10, 20], 5, -1, True
        )
        self.assertFalse(ok)

    def test_boolean_ammo_rejected(self):
        ok, msg = validate_observation(
            "bottom_1", "up", [10, 20], True, False, True
        )
        self.assertFalse(ok)
        self.assertIn("integer", msg.lower())

    def test_float_ammo_rejected(self):
        ok, msg = validate_observation(
            "bottom_1", "up", [10, 20], 40.0, 39.0, True
        )
        self.assertFalse(ok)

    def test_all_eight_expected_positions_have_direction_and_lane(self):
        self.assertEqual(len(EXPECTED), 8)
        for pos_id, info in EXPECTED.items():
            self.assertIn(info["direction"], ("up", "down", "left", "right"))
            self.assertIsInstance(info["lane"], int)
            self.assertGreaterEqual(info["lane"], 0)
            self.assertLess(info["lane"], 35)


if __name__ == "__main__":
    unittest.main(verbosity=2)
