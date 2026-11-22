import json
import unittest
from pathlib import Path

from reachability_auditor import audit, trace_lane

LEVEL39_FILES = (
    Path("data/vision_level39.json"),
    Path("data/conveyor_calibration.json"),
    Path("data/conveyor_visual_observations.json"),
)
HAS_LEVEL39_DATA = all(path.is_file() for path in LEVEL39_FILES)


class ReachabilityAuditorTests(unittest.TestCase):

    def test_matching_run_until_blocker(self):
        board = [
            ["white"],
            ["white"],
            ["red"],
            ["white"],
            ["white"],
        ]

        result = trace_lane(board, (0, 0), "down", "white")

        self.assertEqual(
            result["status"], "MATCHING_RUN_THEN_BLOCKED"
        )
        self.assertEqual(result["exposed_matching_count"], 2)
        self.assertEqual(result["first_blocker"]["colour"], "red")
        self.assertEqual(
            result["matching_tiles_behind_blocker_count"], 2
        )

    def test_different_colour_at_first_cell(self):
        board = [["red"], ["white"], ["white"]]

        result = trace_lane(board, (0, 0), "down", "white")

        self.assertEqual(
            result["status"], "BLOCKED_BY_DIFFERENT_COLOUR"
        )
        self.assertEqual(result["exposed_matching_count"], 0)
        self.assertEqual(
            result["matching_tiles_behind_blocker_count"], 2
        )

    def test_entire_lane_matches(self):
        board = [["white"], ["white"], ["white"]]

        result = trace_lane(board, (0, 0), "down", "white")

        self.assertEqual(result["status"], "EXPOSED_MATCHING_RUN")
        self.assertEqual(result["exposed_matching_count"], 3)
        self.assertIsNone(result["first_blocker"])

    def test_no_matching_tiles(self):
        board = [["red"], ["blue"], ["green"]]

        result = trace_lane(board, (0, 0), "down", "white")

        self.assertEqual(result["status"], "BLOCKED_BY_DIFFERENT_COLOUR")
        self.assertEqual(result["exposed_matching_count"], 0)

    def test_invalid_first_cell_rejected(self):
        with self.assertRaises(ValueError):
            trace_lane([["white"]], (1, 0), "down", "white")

    def test_invalid_direction_rejected(self):
        with self.assertRaises(ValueError):
            trace_lane([["white"]], (0, 0), "diagonal", "white")

    @unittest.skipUnless(HAS_LEVEL39_DATA, "Private Level 39 evidence is not included in the public repository")
    def test_actual_level39_has_eight_positions(self):
        board = json.loads(LEVEL39_FILES[0].read_text())
        calibration = json.loads(LEVEL39_FILES[1].read_text())
        observations = json.loads(LEVEL39_FILES[2].read_text())

        report = audit(board, calibration, observations)

        self.assertEqual(len(report["results"]), 8)
        self.assertTrue(
            all(item["scenarios"] for item in report["results"])
        )

    @unittest.skipUnless(HAS_LEVEL39_DATA, "Private Level 39 evidence is not included in the public repository")
    def test_blue_observations_have_two_scenarios(self):
        board = json.loads(LEVEL39_FILES[0].read_text())
        calibration = json.loads(LEVEL39_FILES[1].read_text())
        observations = json.loads(LEVEL39_FILES[2].read_text())

        report = audit(board, calibration, observations)

        for item in report["results"]:
            if item.get("observed_colour") == "blue":
                self.assertEqual(
                    item["candidate_board_colours"],
                    ["blue", "cyan"]
                )
                self.assertEqual(len(item["scenarios"]), 2)

    @unittest.skipUnless(HAS_LEVEL39_DATA, "Private Level 39 evidence is not included in the public repository")
    def test_safety_flags_remain_false(self):
        board = json.loads(LEVEL39_FILES[0].read_text())
        calibration = json.loads(LEVEL39_FILES[1].read_text())
        observations = json.loads(LEVEL39_FILES[2].read_text())

        report = audit(board, calibration, observations)

        self.assertFalse(report["gameplay_verified"])
        self.assertFalse(report["game_taps_enabled"])
        self.assertFalse(report["conveyor_identity_verified"])

    @unittest.skipUnless(HAS_LEVEL39_DATA, "Private Level 39 evidence is not included in the public repository")
    def test_old_or_unmatched_observations_are_not_planning_eligible(self):
        board = json.loads(LEVEL39_FILES[0].read_text())
        calibration = json.loads(LEVEL39_FILES[1].read_text())
        observations = json.loads(LEVEL39_FILES[2].read_text())

        report = audit(board, calibration, observations)

        self.assertFalse(report["same_board_state_confirmed"])
        self.assertEqual(report["planning_ready_positions"], 0)
        self.assertTrue(
            all(not item["planning_eligible"]
                for item in report["results"])
        )

    @unittest.skipUnless(HAS_LEVEL39_DATA, "Private Level 39 evidence is not included in the public repository")
    def test_zero_ammunition_is_never_eligible(self):
        board = json.loads(LEVEL39_FILES[0].read_text())
        calibration = json.loads(LEVEL39_FILES[1].read_text())
        observations = json.loads(LEVEL39_FILES[2].read_text())

        report = audit(board, calibration, observations)
        zero_ammo = [
            item for item in report["results"]
            if item.get("observed_ammo") == 0
        ]

        self.assertTrue(zero_ammo)
        self.assertTrue(
            all(not item["ammunition_available"]
                and not item["planning_eligible"]
                for item in zero_ammo)
        )

if __name__ == "__main__":
    unittest.main(verbosity=2)
