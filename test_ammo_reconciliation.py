import unittest

from ammo_reconciliation import (
    reconcile_simulated_ammo,
    validate_ammo_observation,
)


class AmmoReconciliationTests(unittest.TestCase):
    def test_complete_user_confirmed_observation_is_verified(self):
        evidence = validate_ammo_observation(
            "bottom_1",
            12,
            {
                "position_id": "bottom_1",
                "capture_session_id": "capture-1",
                "board_snapshot_id": "board-1",
                "observed_at": "2026-11-23T10:00:00+03:00",
                "ammo_verified_by_user": True,
            },
        )
        self.assertTrue(evidence["verified"])

    def test_missing_confirmation_is_not_verified(self):
        evidence = validate_ammo_observation(
            "bottom_1",
            12,
            {
                "position_id": "bottom_1",
                "capture_session_id": "capture-1",
                "board_snapshot_id": "board-1",
                "observed_at": "2026-11-23T10:00:00+03:00",
            },
        )
        self.assertFalse(evidence["verified"])
        self.assertFalse(evidence["checks"]["explicit_user_confirmation"])

    def test_wrong_position_identity_is_not_verified(self):
        evidence = validate_ammo_observation(
            "bottom_1",
            12,
            {
                "position_id": "right_1",
                "capture_session_id": "capture-1",
                "board_snapshot_id": "board-1",
                "observed_at": "now",
                "ammo_verified_by_user": True,
            },
        )
        self.assertFalse(evidence["verified"])

    def test_boolean_ammo_is_rejected(self):
        evidence = validate_ammo_observation(
            "bottom_1",
            True,
            {"position_id": "bottom_1", "ammo_verified_by_user": True},
        )
        self.assertFalse(evidence["checks"]["ammo_is_non_negative_integer"])

    def test_simulated_ammo_delta_reconciles(self):
        result = reconcile_simulated_ammo(20, 7, 13)
        self.assertTrue(result["consistent"])
        self.assertEqual(result["status"], "RECONCILED")

    def test_simulated_ammo_delta_mismatch_rejected(self):
        result = reconcile_simulated_ammo(20, 7, 14)
        self.assertFalse(result["consistent"])
        self.assertEqual(result["status"], "AMMUNITION_DELTA_MISMATCH")

    def test_simulation_cannot_spend_more_than_available(self):
        result = reconcile_simulated_ammo(3, 4, 0)
        self.assertFalse(result["consistent"])

    def test_negative_counts_rejected(self):
        result = reconcile_simulated_ammo(3, -1, 4)
        self.assertEqual(result["status"], "INVALID_AMMUNITION_COUNTS")


if __name__ == "__main__":
    unittest.main(verbosity=2)
