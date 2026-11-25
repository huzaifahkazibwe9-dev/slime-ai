"""Tests for the evidence-based readiness coordinator."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import readiness_coordinator as readiness


class FakeState:
    def __init__(self, *, width=35, height=35, remaining_pixels=1225,
                 valid=True, mappings_verified=False, accessible=0):
        self.level = 39
        self.shooters = {}
        self.width = width
        self.height = height
        self.remaining_pixels = remaining_pixels
        self.colour_mappings_verified = mappings_verified
        self._valid = valid
        self._accessible = accessible

    def validate(self):
        return [] if self._valid else ["synthetic validation error"]

    def accessible_shooters(self):
        return [object() for _ in range(self._accessible)]


class ReadinessAssessTests(unittest.TestCase):
    def complete_evidence(self):
        return (
            {"initial_occupancy_user_confirmed": True,
             "colour_classification_verified": True,
             "shooter_capture_provenance_verified": True},
            {"shooters": [{"id": "s1"}],
             "timing_calibrated_to_game": True, "verified_by_user": True},
            {"identity_verified": True, "verified_by_user": True,
             "timestamps_known": True, "timestamp_identified": True,
             "errors": [], "blockers": []},
            {"actual_firing_verified": True},
        )

    def test_valid_board_is_diagnostic_ready(self):
        result = readiness.assess(FakeState(), {}, {}, {}, {})
        self.assertTrue(result["diagnostic_ready"])
        self.assertFalse(result["game_taps_enabled"])
        self.assertFalse(result["autonomous_play_ready"])

    def test_wrong_dimensions_block_diagnostic_readiness(self):
        result = readiness.assess(FakeState(width=34), {}, {}, {}, {})
        self.assertFalse(result["diagnostic_ready"])
        self.assertFalse(result["checks"]["board_dimensions_35x35"])

    def test_missing_tile_blocks_diagnostic_readiness(self):
        result = readiness.assess(
            FakeState(remaining_pixels=1224), {}, {}, {}, {}
        )
        self.assertFalse(result["diagnostic_ready"])
        self.assertFalse(
            result["checks"]["all_1225_starting_tiles_preserved"]
        )

    def test_invalid_state_blocks_diagnostic_readiness(self):
        result = readiness.assess(FakeState(valid=False), {}, {}, {}, {})
        self.assertFalse(result["diagnostic_ready"])
        self.assertFalse(result["checks"]["game_state_valid"])
        self.assertEqual(
            result["validation_errors"], ["synthetic validation error"]
        )

    def test_evidence_checks_are_independent(self):
        audit, calibration, identity, firing = self.complete_evidence()
        state = FakeState(mappings_verified=True, accessible=1)
        result = readiness.assess(
            state, audit, calibration, identity, firing
        )
        self.assertTrue(result["checks"]["initial_occupancy_user_confirmed"])
        self.assertTrue(result["checks"]["colour_classification_verified"])
        self.assertTrue(result["checks"]["colour_mappings_gameplay_verified"])
        self.assertTrue(result["checks"]["at_least_one_accessible_shooter"])
        self.assertTrue(result["checks"]["conveyor_calibration_present"])
        self.assertTrue(result["checks"]["conveyor_timing_calibrated"])
        self.assertTrue(result["checks"]["physical_shooter_identity_verified"])
        self.assertTrue(result["checks"]["actual_firing_verified"])

    def test_missing_evidence_stays_pending(self):
        result = readiness.assess(FakeState(), {}, {}, {}, {})
        self.assertFalse(
            result["checks"]["initial_occupancy_user_confirmed"]
        )
        self.assertFalse(
            result["checks"]["physical_shooter_identity_verified"]
        )
        self.assertFalse(result["checks"]["conveyor_timing_calibrated"])

        self.assertFalse(result["checks"]["actual_firing_verified"])

    def test_unverified_identity_and_firing_do_not_pass(self):
        result = readiness.assess(
            FakeState(accessible=1),
            {"initial_occupancy_user_confirmed": True,
             "colour_classification_verified": True},
            {"shooters": [{"id": "s1"}]},
            {"identity_verified": False},
            {"actual_firing_verified": False},
        )
        self.assertFalse(
            result["checks"]["physical_shooter_identity_verified"]
        )
        self.assertFalse(result["checks"]["actual_firing_verified"])

    def test_shooter_calibration_without_timing_confirmation_is_insufficient(self):
        result = readiness.assess(
            FakeState(),
            {},
            {"shooters": [{"id": "s1"}], "verified_by_user": True},
            {},
            {},
        )
        self.assertTrue(result["checks"]["conveyor_calibration_present"])
        self.assertFalse(result["checks"]["conveyor_timing_calibrated"])

    def test_gameplay_never_becomes_ready_from_evidence_flags(self):
        audit, calibration, identity, firing = self.complete_evidence()
        result = readiness.assess(
            FakeState(mappings_verified=True, accessible=1),
            audit, calibration, identity, firing
        )
        evidence_checks = {
            key: value for key, value in result["checks"].items()
            if key not in {
                "live_execution_path_implemented",
                "live_gameplay_validation_complete",
                "explicit_live_execution_opt_in",
            }
        }
        self.assertTrue(all(evidence_checks.values()))
        self.assertFalse(result["checks"]["live_execution_path_implemented"])
        self.assertFalse(result["checks"]["live_gameplay_validation_complete"])
        self.assertFalse(result["checks"]["explicit_live_execution_opt_in"])
        self.assertEqual(
            result["live_execution_blockers"],
            [
                "live_execution_path_implemented",
                "live_gameplay_validation_complete",
                "explicit_live_execution_opt_in",
            ],
        )
        self.assertFalse(result["game_taps_enabled"])
        self.assertFalse(result["autonomous_play_ready"])


class ReadinessPlannerIntegrationTests(unittest.TestCase):
    def test_matching_bundle_still_blocks_without_shooter_capture_provenance(self):
        reports = {
            "conveyor_calibration.json": {},
            "identity_audit_report.json": {},
            "firing_observations.json": {},
            "planning_gate_latest.json": {},
            "conveyor_identity_candidates.json": {},
            "snapshot_sync_report.json": {
                "synchronised": True,
                "planning_allowed_by_sync": True,
            },
        }
        valid_bundle = {
            "synchronised": True,
            "planning_allowed_by_sync": True,
        }
        passed_gate = {"evidence_gate_passed": True}
        with tempfile.TemporaryDirectory() as directory:
            with (
                patch.object(readiness, "DATA", Path(directory)),
                patch.object(readiness, "REPORT", Path(directory) / "readiness_report.json"),
                patch.object(readiness, "load_level",
                             return_value=(FakeState(), {
                                 "shooter_capture_provenance_verified": False
                             })),
                patch.object(readiness, "read_json",
                             side_effect=lambda name, default=None:
                             reports.get(name, default)),
                patch.object(readiness, "learning_summary",
                             return_value={"available": False,
                                           "gameplay_records": 0}),
                patch("snapshot_sync.synchronise_bundle",
                      return_value=valid_bundle),
                patch("orchestration.evidence_status",
                      return_value=passed_gate),
                patch.object(readiness, "plan_next_move",
                             return_value=None) as planner,
            ):
                readiness.main(observation_path="board.json",
                               shooter_path="shooters.json")

            planner.assert_not_called()
            report = json.loads(
                (Path(directory) / "readiness_report.json").read_text()
            )
            self.assertFalse(report["shooter_capture_provenance_verified"])
            self.assertIsNone(report["planner_candidate"])

    def test_missing_capture_bundle_blocks_readiness_planner(self):
        reports = {
            "conveyor_calibration.json": {"timing_calibrated_to_game": True},
            "identity_audit_report.json": {"identity_verified": True},
            "firing_observations.json": {"actual_firing_verified": True},
            "planning_gate_latest.json": {"report": "planning"},
            "conveyor_identity_candidates.json": {"report": "candidates"},
            "snapshot_sync_report.json": {
                "synchronised": True,
                "planning_allowed_by_sync": True,
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            with (
                patch.object(readiness, "DATA", Path(directory)),
                patch.object(readiness, "REPORT", Path(directory) / "readiness_report.json"),
                patch.object(readiness, "load_level",
                             return_value=(FakeState(), {})),
                patch.object(readiness, "read_json",
                             side_effect=lambda name, default=None:
                             reports.get(name, default)),
                patch.object(readiness, "learning_summary",
                             return_value={"available": False,
                                           "gameplay_records": 0}),
                patch.object(readiness, "plan_next_move",
                             return_value=None) as planner,
            ):
                readiness.main(observation_path="board.json",
                               shooter_path="shooters.json")

            planner.assert_not_called()
            report = json.loads(
                (Path(directory) / "readiness_report.json").read_text()
            )
            self.assertFalse(
                report["planning_evidence_gate"]["evidence_gate_passed"]
            )
            self.assertFalse(
                report["evidence_bundle_synchronisation"]["synchronised"]
            )
            self.assertIsNone(report["planner_candidate"])


class LearningSummaryTests(unittest.TestCase):
    def test_missing_database_is_reported_without_creation(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(readiness, "DATA", Path(directory)):
                result = readiness.learning_summary()
            self.assertEqual(
                result, {"available": False, "gameplay_records": 0}
            )
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_database_without_observations_table_is_safe(self):
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory)
            connection = sqlite3.connect(data / "learning.db")
            connection.execute("CREATE TABLE other_table (id INTEGER)")
            connection.commit()
            connection.close()
            with patch.object(readiness, "DATA", data):
                result = readiness.learning_summary()
        self.assertTrue(result["available"])
        self.assertEqual(result["gameplay_records"], 0)
        self.assertIn("note", result)

    def test_gameplay_record_count_is_read_only(self):
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory)
            connection = sqlite3.connect(data / "learning.db")
            connection.execute(
                "CREATE TABLE observations "
                "(id INTEGER PRIMARY KEY, source TEXT)"
            )
            connection.executemany(
                "INSERT INTO observations(source) VALUES (?)",
                [("gameplay",), ("synthetic",), ("gameplay",)],
            )
            connection.commit()
            connection.close()

            with patch.object(readiness, "DATA", data):
                result = readiness.learning_summary()

            self.assertEqual(
                result, {"available": True, "gameplay_records": 2}
            )
            connection = sqlite3.connect(data / "learning.db")
            count = connection.execute(
                "SELECT COUNT(*) FROM observations"
            ).fetchone()[0]
            connection.close()
            self.assertEqual(count, 3)


    def test_malformed_evidence_shapes_fail_closed_without_crashing(self):
        result = readiness.assess(
            FakeState(),
            ["not", "an", "object"],
            {"shooters": {"not": "a list"}, "timing_calibrated_to_game": True,
             "verified_by_user": True},
            ["not", "an", "object"],
            ["not", "an", "object"],
        )
        self.assertFalse(result["checks"]["initial_occupancy_user_confirmed"])
        self.assertFalse(result["checks"]["conveyor_calibration_present"])
        self.assertFalse(result["checks"]["conveyor_timing_calibrated"])
        self.assertFalse(result["checks"]["physical_shooter_identity_verified"])
        self.assertFalse(result["checks"]["actual_firing_verified"])

    def test_read_json_rejects_unreadable_utf8_payloads(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "invalid.json").write_bytes(b"\\xff\\xfe")
            with patch.object(readiness, "DATA", root):
                self.assertEqual(readiness.read_json("invalid.json", {}), {})

    def test_read_json_rejects_non_object_top_level_payloads(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "array.json").write_text("[]")
            with patch.object(readiness, "DATA", root):
                self.assertEqual(readiness.read_json("array.json", {}), {})

    def test_physical_identity_requires_user_confirmation_and_timestamps(self):
        state = FakeState()
        for field, value in (
            ("verified_by_user", False),
            ("timestamps_known", False),
            ("timestamp_identified", False),
            ("errors", ["bad"]),
            ("blockers", ["bad"]),
        ):
            identity = {
                "identity_verified": True, "verified_by_user": True,
                "timestamps_known": True, "timestamp_identified": True,
                "errors": [], "blockers": [],
            }
            identity[field] = value
            result = readiness.assess(state, {}, {}, identity, {})
            self.assertFalse(result["checks"]["physical_shooter_identity_verified"])

if __name__ == "__main__":
    unittest.main()
