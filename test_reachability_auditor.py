import json
import runpy
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

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

    def test_screenshot_observation_can_feed_lane_analysis(self):
        board = [["white"] * 35 for _ in range(35)]
        board[2][15] = "red"
        board_data = {
            "board": board,
            "snapshot_id": "sha256:" + "d" * 64,
            "timestamp_identified": False,
        }
        calibration = {
            "verified_by_user": True,
            "image_size": [1080, 2220],
            "shooters": [{
                "id": "top_1",
                "segment": "top",
                "center": [500, 179],
            }],
            "directions": {"top": "down"},
        }
        observations = {
            "observations": [{
                "position_id": "top_1",
                "colour": "white",
                "ammo": 40,
            }],
            "timestamp_identified": False,
            "identity_verified": False,
            "gameplay_verified": False,
            "board_snapshot_id": None,
            "same_board_state_confirmed": False,
        }
        report = audit(board_data, calibration, observations)
        position = report["results"][0]
        self.assertEqual(position["position_id"], "top_1")
        self.assertEqual(position["scenarios"][0]["exposed_matching_count"], 2)
        self.assertEqual(
            position["scenarios"][0]["status"],
            "MATCHING_RUN_THEN_BLOCKED",
        )
        self.assertEqual(report["planning_ready_positions"], 0)
        self.assertFalse(report["same_board_state_confirmed"])
        self.assertFalse(report["gameplay_verified"])
        self.assertFalse(report["game_taps_enabled"])

    def test_ammo_reading_without_explicit_provenance_is_unverified(self):
        # The calibrated top shooter geometry targets column 15 of row 0;
        # use the real 35x35 board dimensions rather than a 3x1 stub.
        board = [["white"] * 35 for _ in range(35)]
        board_data = {
            "board": board,
            "snapshot_id": "board-1",
            "timestamp_identified": True,
        }
        calibration = {
            "verified_by_user": True,
            "image_size": [1080, 2220],
            "shooters": [{
                "id": "top_1",
                "segment": "top",
                "center": [500, 179],
            }],
        }
        observations = {
            "observations": [{
                "position_id": "top_1",
                "colour": "white",
                "ammo": 5,
            }],
            "timestamp_identified": True,
            "identity_verified": True,
            "gameplay_verified": True,
            "board_snapshot_id": "board-1",
            "same_board_state_confirmed": True,
        }
        report = audit(board_data, calibration, observations)
        position = report["results"][0]
        self.assertFalse(position["ammo_evidence"]["verified"])
        self.assertFalse(position["ammunition_evidence_verified"])
        self.assertFalse(position["planning_eligible"])
        self.assertFalse(report["capture_freshness"]["fresh"])
        self.assertIn(
            "AMMUNITION_OBSERVATION_UNVERIFIED",
            position["planning_blockers"],
        )

    def test_cli_traces_screenshot_observation_without_unlocking_planning(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            board = [["white"] * 35 for _ in range(35)]
            board[2][15] = "red"
            rgb = [
                [[245, 245, 245] for _ in range(35)]
                for _ in range(35)
            ]
            rgb[2][15] = [230, 30, 30]
            counts = {"white": 1224, "red": 1}
            board_data = {
                "image_size": [1080, 2220],
                "grid_size": [35, 35],
                "bounds": [201, 431, 881, 1113],
                "board": board,
                "raw_rgb": rgb,
                "counts": counts,
                "source_sha256": "e" * 64,
                "snapshot_id": "sha256:" + "e" * 64,
                "timestamp_identified": False,
                "gameplay_verified": False,
                "vision_classification_verified": False,
                "game_taps_enabled": False,
            }
            calibration = {
                "verified_by_user": True,
                "image_size": [1080, 2220],
                "shooters": [{
                    "id": "top_1",
                    "segment": "top",
                    "center": [500, 179],
                }],
                "directions": {"top": "down"},
            }
            observations = {
                "observations": [{
                    "position_id": "top_1",
                    "colour": "white",
                    "ammo": 40,
                }],
                "timestamp_identified": False,
                "identity_verified": False,
                "gameplay_verified": False,
                "board_snapshot_id": None,
                "same_board_state_confirmed": False,
            }
            board_path = root / "board.json"
            calibration_path = root / "calibration.json"
            observations_path = root / "observations.json"
            output_path = root / "report.json"
            board_path.write_text(json.dumps(board_data))
            calibration_path.write_text(json.dumps(calibration))
            observations_path.write_text(json.dumps(observations))

            argv = [
                "reachability_auditor.py",
                "--board", str(board_path),
                "--calibration", str(calibration_path),
                "--observations", str(observations_path),
                "--output", str(output_path),
            ]
            output = StringIO()
            with patch.object(sys, "argv", argv), redirect_stdout(output):
                runpy.run_module("reachability_auditor", run_name="__main__")

            report = json.loads(output_path.read_text())
            self.assertEqual(report["board_snapshot_id"], board_data["snapshot_id"])
            self.assertEqual(report["planning_ready_positions"], 0)
            self.assertFalse(report["gameplay_verified"])
            self.assertFalse(report["game_taps_enabled"])
            self.assertIn("Board colour truth verified: False", output.getvalue())

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
