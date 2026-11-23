import unittest

from planning_gate import evaluate_planning


def make_report():
    return {
        "level": 39,
        "board_dimensions": [2, 2],
        "same_board_state_confirmed": False,
        "conveyor_identity_verified": False,
        "gameplay_verified": False,
        "confidence_audit": {"game_taps_enabled": False},
        "results": [{
            "position_id": "left_2",
            "observed_ammo": 0,
            "identity_verified": False,
            "planning_eligible": False,
            "scenarios": [{
                "target_colour": "cyan",
                "status": "EXPOSED_MATCHING_RUN",
                "exposed_matching_count": 2,
                "confidence_eligible": False,
                "planning_eligible": False,
            }],
        }],
    }


class PlanningGateTests(unittest.TestCase):
    def test_zero_ammunition_rejected(self):
        result = evaluate_planning(make_report())
        item = result["results"][0]
        self.assertFalse(item["ammunition_available"])
        self.assertIn("NO_REMAINING_AMMUNITION", item["blockers"])
        self.assertFalse(item["planning_eligible"])

    def test_geometry_is_separate_from_eligibility(self):
        result = evaluate_planning(make_report())
        item = result["results"][0]
        self.assertTrue(item["geometrically_reachable"])
        self.assertFalse(item["planning_eligible"])

    def test_unverified_identity_rejected(self):
        result = evaluate_planning(make_report())
        self.assertIn(
            "SHOOTER_IDENTITY_UNVERIFIED",
            result["results"][0]["blockers"],
        )

    def test_unverified_mapping_rejected(self):
        result = evaluate_planning(make_report())
        self.assertIn(
            "GAMEPLAY_COLOUR_MAPPING_UNVERIFIED",
            result["results"][0]["blockers"],
        )

    def test_unsynchronised_board_rejected(self):
        result = evaluate_planning(make_report())
        self.assertIn(
            "BOARD_STATE_NOT_SYNCHRONISED",
            result["results"][0]["blockers"],
        )

    def test_unconfirmed_lane_rejected(self):
        result = evaluate_planning(make_report())
        self.assertIn(
            "LANE_CONFIDENCE_UNCONFIRMED",
            result["results"][0]["blockers"],
        )

    def test_no_matching_pixels_rejected(self):
        report = make_report()
        report["results"][0]["scenarios"][0]["exposed_matching_count"] = 0
        result = evaluate_planning(report)
        self.assertFalse(result["results"][0]["geometrically_reachable"])
        self.assertIn(
            "NO_EXPOSED_MATCHING_PIXELS",
            result["results"][0]["blockers"],
        )

    def test_all_gates_must_pass(self):
        report = make_report()
        report["same_board_state_confirmed"] = True
        report["conveyor_identity_verified"] = True
        report["gameplay_verified"] = True
        position = report["results"][0]
        position["observed_ammo"] = 10
        position["identity_verified"] = True
        position["planning_eligible"] = True
        scenario = position["scenarios"][0]
        scenario["confidence_eligible"] = True
        scenario["planning_eligible"] = True

        result = evaluate_planning(report)
        self.assertTrue(result["results"][0]["planning_eligible"])
        self.assertEqual(result["counts"]["eligible_scenarios"], 1)

    def test_unverified_ammo_provenance_rejected(self):
        report = make_report()
        position = report["results"][0]
        position["observed_ammo"] = 8
        position["identity_verified"] = True
        position["planning_eligible"] = True
        report["same_board_state_confirmed"] = True
        report["conveyor_identity_verified"] = True
        report["gameplay_verified"] = True
        scenario = position["scenarios"][0]
        scenario["confidence_eligible"] = True
        scenario["planning_eligible"] = True
        result = evaluate_planning(report)
        item = result["results"][0]
        self.assertFalse(item["planning_eligible"])
        self.assertIn(
            "AMMUNITION_OBSERVATION_UNVERIFIED",
            item["blockers"],
        )

    def test_safety_flags_always_disabled(self):
        result = evaluate_planning(make_report())
        self.assertFalse(result["gameplay_verified"])
        self.assertFalse(result["game_taps_enabled"])
        self.assertFalse(result["actions_performed"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
