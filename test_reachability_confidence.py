import unittest

from reachability_confidence import annotate_report


def sample_report():
    return {
        "board_dimensions": [2, 2],
        "game_taps_enabled": False,
        "results": [{
            "position_id": "test",
            "scenarios": [{
                "target_colour": "white",
                "planning_eligible": False,
                "lane_cells": [
                    {"row": 0, "column": 0},
                    {"row": 1, "column": 0},
                ],
            }],
        }],
    }


class ReachabilityConfidenceTests(unittest.TestCase):
    def test_confidence_labels_attached_to_lane_cells(self):
        report = annotate_report(
            sample_report(),
            [["confirmed", "provisional"],
             ["requires_confirmation", "confirmed"]],
        )
        cells = report["results"][0]["scenarios"][0]["lane_cells"]
        self.assertEqual(
            [cell["confidence_status"] for cell in cells],
            ["confirmed", "requires_confirmation"],
        )

    def test_unconfirmed_lane_is_not_confidence_eligible(self):
        report = annotate_report(
            sample_report(),
            [["confirmed", "provisional"],
             ["requires_confirmation", "confirmed"]],
        )
        scenario = report["results"][0]["scenarios"][0]
        self.assertFalse(scenario["confidence_eligible"])
        self.assertFalse(scenario["planning_eligible"])

    def test_all_confirmed_lane_can_be_confidence_eligible(self):
        report = annotate_report(
            sample_report(),
            [["confirmed", "confirmed"],
             ["confirmed", "confirmed"]],
        )
        scenario = report["results"][0]["scenarios"][0]
        self.assertTrue(scenario["confidence_eligible"])
        # This layer must never upgrade previous planning eligibility.
        self.assertFalse(scenario["planning_eligible"])

    def test_unknown_cells_remain_ineligible(self):
        report = annotate_report(
            sample_report(),
            [["confirmed", "confirmed"],
             ["unknown", "confirmed"]],
        )
        scenario = report["results"][0]["scenarios"][0]
        self.assertFalse(scenario["confidence_eligible"])
        self.assertEqual(
            scenario["confidence_cell_counts"]["unknown"], 1
        )

    def test_dimension_mismatch_rejected(self):
        with self.assertRaises(ValueError):
            annotate_report(sample_report(), [["confirmed"]])

    def test_safety_flags_remain_disabled(self):
        report = annotate_report(
            sample_report(),
            [["confirmed", "confirmed"],
             ["confirmed", "confirmed"]],
        )
        self.assertFalse(report["confidence_audit"]["gameplay_verified"])
        self.assertFalse(report["confidence_audit"]["game_taps_enabled"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
