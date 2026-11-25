import hashlib
import json
import runpy
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from reachability_confidence import (
    annotate_report, observation_confidence, validate_edge_confidence_source,
    validate_board_observation_source,
)


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

    def test_screenshot_observation_cells_remain_provisional(self):
        board = [["white"] * 35 for _ in range(35)]
        confidence = observation_confidence(board)
        self.assertEqual(len(confidence), 35)
        self.assertEqual(len(confidence[0]), 35)
        self.assertEqual(
            sum(cell == "requires_confirmation" for row in confidence for cell in row),
            136,
        )
        self.assertEqual(
            sum(cell == "provisional" for row in confidence for cell in row),
            1089,
        )
        self.assertFalse(any(
            cell == "confirmed" for row in confidence for cell in row
        ))

    def test_screenshot_confidence_blocks_every_unverified_lane(self):
        confidence = observation_confidence([["white"] * 35 for _ in range(35)])
        report = {
            "board_dimensions": [35, 35],
            "game_taps_enabled": False,
            "results": [{
                "position_id": "top_1",
                "scenarios": [{
                    "target_colour": "white",
                    "planning_eligible": True,
                    "lane_cells": [
                        {"row": 0, "column": 15},
                        {"row": 1, "column": 15},
                        {"row": 2, "column": 15},
                    ],
                }],
            }],
        }
        annotated = annotate_report(report, confidence)
        scenario = annotated["results"][0]["scenarios"][0]
        self.assertFalse(scenario["confidence_eligible"])
        self.assertFalse(scenario["planning_eligible"])
        self.assertEqual(
            scenario["confidence_cell_counts"],
            {"provisional": 2, "requires_confirmation": 1},
        )
        self.assertFalse(annotated["confidence_audit"]["gameplay_verified"])
        self.assertFalse(annotated["confidence_audit"]["game_taps_enabled"])

    def test_cli_uses_screenshot_board_confidence(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            board = [["white"] * 35 for _ in range(35)]
            rgb = [[[245, 245, 245] for _ in range(35)] for _ in range(35)]
            board_data = {
                "image_size": [1080, 2220],
                "grid_size": [35, 35],
                "bounds": [201, 431, 881, 1113],
                "board": board,
                "raw_rgb": rgb,
                "counts": {"white": 1225},
                "source_sha256": "9" * 64,
                "snapshot_id": "sha256:" + "9" * 64,
                "board_snapshot_id": "sha256:" + "9" * 64,
                "gameplay_verified": False,
                "vision_classification_verified": False,
                "game_taps_enabled": False,
            }
            reachability = {
                "board_dimensions": [35, 35],
                "board_source_kind": "screenshot_observation",
                "board_snapshot_id": "sha256:" + "9" * 64,
                "source_file_sha256": {
                    "board_json": "a" * 64,
                    "conveyor_calibration_json": "b" * 64,
                    "conveyor_observations_json": "c" * 64,
                },
                "game_taps_enabled": False,
                "results": [{
                    "position_id": "top_1",
                    "scenarios": [{
                        "target_colour": "white",
                        "planning_eligible": True,
                        "lane_cells": [
                            {"row": 0, "column": 15},
                            {"row": 1, "column": 15},
                        ],
                    }],
                }],
            }
            board_path = root / "board.json"
            input_path = root / "reachability.json"
            output_path = root / "confidence.json"
            board_path.write_text(json.dumps(board_data))
            reachability["source_file_sha256"]["board_json"] = hashlib.sha256(
                board_path.read_bytes()
            ).hexdigest()
            input_path.write_text(json.dumps(reachability))
            argv = [
                "reachability_confidence.py",
                "--input", str(input_path),
                "--board", str(board_path),
                "--output", str(output_path),
            ]
            output = StringIO()
            with patch.object(sys, "argv", argv), redirect_stdout(output):
                runpy.run_module("reachability_confidence", run_name="__main__")
            result = json.loads(output_path.read_text())
            scenario = result["results"][0]["scenarios"][0]
            self.assertFalse(scenario["confidence_eligible"])
            self.assertFalse(scenario["planning_eligible"])
            self.assertFalse(result["confidence_audit"]["game_taps_enabled"])
            self.assertTrue(result["confidence_audit"]["snapshot_match_verified"])
            self.assertEqual(
                result["confidence_audit"]["source_snapshot_id"],
                result["board_snapshot_id"],
            )
            self.assertEqual(
                result["upstream_source_file_sha256"],
                reachability["source_file_sha256"],
            )
            self.assertEqual(
                result["upstream_source_kind"],
                "screenshot_observation",
            )
            self.assertEqual(
                result["source_file_sha256"],
                {
                    "reachability_audit_json": hashlib.sha256(
                        input_path.read_bytes()
                    ).hexdigest(),
                    "board_observation_json": hashlib.sha256(
                        board_path.read_bytes()
                    ).hexdigest(),
                },
            )

    def test_confidence_cli_rejects_different_board_snapshot(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            board = [["white"] * 35 for _ in range(35)]
            rgb = [[[245, 245, 245] for _ in range(35)] for _ in range(35)]
            board_data = {
                "image_size": [1080, 2220],
                "grid_size": [35, 35],
                "bounds": [201, 431, 881, 1113],
                "board": board,
                "raw_rgb": rgb,
                "counts": {"white": 1225},
                "source_sha256": "a" * 64,
                "snapshot_id": "sha256:" + "a" * 64,
                "board_snapshot_id": "sha256:" + "a" * 64,
                "gameplay_verified": False,
                "vision_classification_verified": False,
                "game_taps_enabled": False,
            }
            reachability = {
                "board_dimensions": [35, 35],
                "board_snapshot_id": "sha256:" + "b" * 64,
                "results": [],
            }
            board_path = root / "board.json"
            input_path = root / "reachability.json"
            board_path.write_text(json.dumps(board_data))
            input_path.write_text(json.dumps(reachability))
            argv = [
                "reachability_confidence.py",
                "--input", str(input_path),
                "--board", str(board_path),
                "--output", str(root / "confidence.json"),
            ]
            with patch.object(sys, "argv", argv), self.assertRaisesRegex(
                ValueError, "snapshot does not match"
            ):
                runpy.run_module("reachability_confidence", run_name="__main__")

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

    def test_reachability_board_source_requires_exact_bytes(self):
        digest = "a" * 64
        self.assertTrue(validate_board_observation_source(
            {"source_file_sha256": {"board_json": digest}},
            digest,
        ))

    def test_reachability_board_source_rejects_missing_or_stale_digest(self):
        digest = "a" * 64
        for report in (
            {},
            {"source_file_sha256": {}},
            {"source_file_sha256": {"board_json": "b" * 64}},
        ):
            with self.subTest(report=report), self.assertRaisesRegex(
                ValueError, "do not match"
            ):
                validate_board_observation_source(report, digest)

    def test_edge_confidence_requires_matching_board_digest(self):
        digest = "a" * 64
        self.assertTrue(validate_edge_confidence_source(
            {"source_file_sha256": {"vision_level39_json": digest}},
            digest,
        ))

    def test_edge_confidence_rejects_missing_or_stale_board_digest(self):
        digest = "a" * 64
        for report in (
            {},
            {"source_file_sha256": {}},
            {"source_file_sha256": {"vision_level39_json": "b" * 64}},
        ):
            with self.subTest(report=report), self.assertRaisesRegex(
                ValueError, "does not match"
            ):
                validate_edge_confidence_source(report, digest)


if __name__ == "__main__":
    unittest.main(verbosity=2)
