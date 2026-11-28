"""Unit tests for identity_tracker.validate_observations.

Uses injected shooters/positions so tests never depend on private
data files. Covers missing fields, unknown IDs, per-frame uniqueness,
and the strict verified=True requirement.
"""

import unittest

from identity_tracker import validate_observations


class IdentityTrackerValidationTests(unittest.TestCase):
    def setUp(self):
        self.shooters = {
            "top_1": {"id": "top_1"},
            "top_2": {"id": "top_2"},
            "bottom_1": {"id": "bottom_1"},
            "left_1": {"id": "left_1"},
        }
        self.positions = {
            "top_1": {"id": "top_1"},
            "top_2": {"id": "top_2"},
            "bottom_1": {"id": "bottom_1"},
            "left_1": {"id": "left_1"},
        }

    def _obs(self, frame_id="f1", position_id="top_1", shooter_id="top_1",
             verified=True):
        return {
            "frame_id": frame_id,
            "position_id": position_id,
            "shooter_id": shooter_id,
            "verified": verified,
        }

    def test_valid_single_observation_accepted(self):
        errors = validate_observations(
            [self._obs()], self.shooters, self.positions
        )
        self.assertEqual(errors, [])

    def test_valid_multiple_frames_accepted(self):
        observations = [
            self._obs("f1", "top_1", "top_1"),
            self._obs("f2", "bottom_1", "bottom_1"),
        ]
        errors = validate_observations(
            observations, self.shooters, self.positions
        )
        self.assertEqual(errors, [])

    def test_same_position_different_frames_accepted(self):
        observations = [
            self._obs("f1", "top_1", "top_1"),
            self._obs("f2", "top_1", "top_2"),
        ]
        errors = validate_observations(
            observations, self.shooters, self.positions
        )
        self.assertEqual(errors, [])

    def test_missing_frame_id_rejected(self):
        obs = self._obs()
        obs["frame_id"] = ""
        errors = validate_observations([obs], self.shooters, self.positions)
        self.assertTrue(any("missing frame_id" in e for e in errors))

    def test_none_frame_id_rejected(self):
        obs = self._obs()
        obs["frame_id"] = None
        errors = validate_observations([obs], self.shooters, self.positions)
        self.assertTrue(any("missing frame_id" in e for e in errors))

    def test_unknown_position_rejected(self):
        errors = validate_observations(
            [self._obs(position_id="unknown_slot")],
            self.shooters,
            self.positions,
        )
        self.assertTrue(any("unknown position" in e for e in errors))

    def test_unknown_shooter_rejected(self):
        errors = validate_observations(
            [self._obs(shooter_id="ghost")],
            self.shooters,
            self.positions,
        )
        self.assertTrue(any("unknown shooter" in e for e in errors))

    def test_duplicate_position_within_frame_rejected(self):
        observations = [
            self._obs("f1", "top_1", "top_1"),
            self._obs("f1", "top_1", "top_2"),
        ]
        errors = validate_observations(
            observations, self.shooters, self.positions
        )
        self.assertTrue(any("duplicate position" in e for e in errors))

    def test_duplicate_shooter_within_frame_rejected(self):
        observations = [
            self._obs("f1", "top_1", "top_1"),
            self._obs("f1", "top_2", "top_1"),
        ]
        errors = validate_observations(
            observations, self.shooters, self.positions
        )
        self.assertTrue(any("duplicate shooter" in e for e in errors))

    def test_unverified_false_rejected(self):
        errors = validate_observations(
            [self._obs(verified=False)],
            self.shooters,
            self.positions,
        )
        self.assertTrue(any("unverified identity" in e for e in errors))

    def test_unverified_missing_key_rejected(self):
        obs = self._obs()
        del obs["verified"]
        errors = validate_observations([obs], self.shooters, self.positions)
        self.assertTrue(any("unverified identity" in e for e in errors))

    def test_unverified_string_true_rejected(self):
        # Strict: only boolean True is accepted
        errors = validate_observations(
            [self._obs(verified="true")],
            self.shooters,
            self.positions,
        )
        self.assertTrue(any("unverified identity" in e for e in errors))

    def test_unverified_integer_one_rejected(self):
        errors = validate_observations(
            [self._obs(verified=1)],
            self.shooters,
            self.positions,
        )
        self.assertTrue(any("unverified identity" in e for e in errors))

    def test_empty_observations_list_accepted(self):
        errors = validate_observations([], self.shooters, self.positions)
        self.assertEqual(errors, [])

    def test_multiple_errors_reported_together(self):
        observations = [
            self._obs("f1", "unknown_pos", "top_1"),
            self._obs("f1", "top_1", "ghost"),
            self._obs("f2", "top_1", "top_1", verified=False),
        ]
        errors = validate_observations(
            observations, self.shooters, self.positions
        )
        self.assertGreaterEqual(len(errors), 3)

    def test_valid_full_frame_of_distinct_pairs(self):
        observations = [
            self._obs("f1", "top_1", "top_1"),
            self._obs("f1", "top_2", "top_2"),
            self._obs("f1", "bottom_1", "bottom_1"),
            self._obs("f1", "left_1", "left_1"),
        ]
        errors = validate_observations(
            observations, self.shooters, self.positions
        )
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
