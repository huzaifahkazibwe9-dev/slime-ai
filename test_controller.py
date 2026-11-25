import json
import hashlib
import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from controller import SlimeController
from orchestration import _canonical_json_sha256


def write_capture_pair(directory, captured_at=None, shooter_hash=None):
    captured_at = captured_at or datetime.now(timezone.utc).isoformat()
    source_hash = "a" * 64
    root = Path(directory)
    calibration = {
        "grid_size": [35, 35],
        "bounds": [201, 431, 881, 1113],
    }
    board = {
        "source_sha256": source_hash,
        "calibration_sha256": _canonical_json_sha256(calibration),
        "snapshot_id": "sha256:" + source_hash,
        "board_snapshot_id": "sha256:" + source_hash,
        "capture_session_id": "session-abc",
        "captured_at": captured_at,
        "image_size": [1080, 2220],
        "grid_size": [35, 35],
    }
    capture_config = {
        "panel_bounds": [100, 200, 300, 400],
        "capture_session_id": "session-abc",
        "captured_at": captured_at,
    }
    capture_config_path = root / "shooter_capture_config.json"
    capture_config_path.write_text(json.dumps(capture_config))
    capture_config_sha256 = hashlib.sha256(
        capture_config_path.read_bytes()
    ).hexdigest()
    shooter = {
        "capture_provenance": {
            "verified": True,
            "source_sha256": shooter_hash or source_hash,
            "capture_session_id": "session-abc",
            "captured_at": captured_at,
            "capture_config_sha256": capture_config_sha256,
            "panel_bounds": [100, 200, 300, 400],
        }
    }
    root = Path(directory)
    (root / "board_observation_latest.json").write_text(json.dumps(board))
    (root / "shooter_detection.json").write_text(json.dumps(shooter))
    audit = {
        "source_sha256": source_hash,
        "image_size": [1080, 2220],
        "grid_size": [35, 35],
        "capture_session_id": "session-abc",
        "captured_at": captured_at,
        "snapshot_id": "sha256:" + source_hash,
        "board_snapshot_id": "sha256:" + source_hash,
        "pixel_samples_reproduced": True,
        "extraction_fingerprint_match": True,
        "label_mismatch_count": 0,
        "colour_counts_match": True,
        "gameplay_verified": False,
        "game_taps_enabled": False,
    }
    (root / "source_pixel_audit_latest.json").write_text(json.dumps(audit))
    # Planning inputs are separate artifacts and are hashed independently.
    evidence_files = {
        "vision_level39.json": calibration,
        "edge_confidence_latest.json": {"fixture": "edge-confidence"},
        "reachability_audit.json": {"fixture": "reachability-audit"},
        "reachability_confidence_latest.json": {"fixture": "reachability-confidence"},
        "conveyor_calibration.json": {"fixture": "conveyor-calibration"},
        "planning_gate_latest.json": {"fixture": "planning"},
        "identity_audit_report.json": {"fixture": "identity"},
        "shooter_identity_observations.json": {"observations": []},
        "bonded_groups_confirmed.json": {
            "verified_by_user": False,
            "bonded_groups": [],
        },
        "shooter_capture_config.json": capture_config,
        "snapshot_sync_report.json": {"fixture": "snapshot"},
        "conveyor_identity_candidates.json": {"fixture": "candidates"},
        "conveyor_visual_observations.json": {"fixture": "conveyor"},
    }
    for name, payload in evidence_files.items():
        (root / name).write_text(json.dumps(payload))
    candidate_path = root / "conveyor_identity_candidates.json"
    candidate = json.loads(candidate_path.read_text())
    candidate["source_file_sha256"] = {
        "conveyor_calibration_json": hashlib.sha256(
            (root / "conveyor_calibration.json").read_bytes()
        ).hexdigest(),
        "conveyor_visual_observations_json": hashlib.sha256(
            (root / "conveyor_visual_observations.json").read_bytes()
        ).hexdigest(),
        "shooter_detection_json": hashlib.sha256(
            (root / "shooter_detection.json").read_bytes()
        ).hexdigest(),
        "identity_audit_json": hashlib.sha256(
            (root / "identity_audit_report.json").read_bytes()
        ).hexdigest(),
        "board_observation_json": hashlib.sha256(
            (root / "board_observation_latest.json").read_bytes()
        ).hexdigest(),
        "shooter_identity_observations_json": hashlib.sha256(
            (root / "shooter_identity_observations.json").read_bytes()
        ).hexdigest(),
        "bonded_groups_config_json": hashlib.sha256(
            (root / "bonded_groups_confirmed.json").read_bytes()
        ).hexdigest(),
    }
    candidate_path.write_text(json.dumps(candidate))



def capture_bundle_hashes(directory):
    root = Path(directory)
    return {
        "board_json": hashlib.sha256(
            (root / "board_observation_latest.json").read_bytes()
        ).hexdigest(),
        "shooter_json": hashlib.sha256(
            (root / "shooter_detection.json").read_bytes()
        ).hexdigest(),
        "pixel_audit_json": hashlib.sha256(
            (root / "source_pixel_audit_latest.json").read_bytes()
        ).hexdigest(),
    }



def planning_evidence_hashes(directory):
    root = Path(directory)
    names = {
        "vision_calibration_json": "vision_level39.json",
        "edge_confidence_json": "edge_confidence_latest.json",
        "reachability_audit_json": "reachability_audit.json",
        "reachability_confidence_json": "reachability_confidence_latest.json",
        "conveyor_calibration_json": "conveyor_calibration.json",
        "planning_json": "planning_gate_latest.json",
        "identity_json": "identity_audit_report.json",
        "snapshot_json": "snapshot_sync_report.json",
        "candidate_json": "conveyor_identity_candidates.json",
        "conveyor_observations_json": "conveyor_visual_observations.json",
        "shooter_detection_json": "shooter_detection.json",
        "identity_observations_json": "shooter_identity_observations.json",
        "bonded_groups_config_json": "bonded_groups_confirmed.json",
        "shooter_capture_config_json": "shooter_capture_config.json",
        "board_observation_json": "board_observation_latest.json",
    }
    return {
        key: hashlib.sha256((root / name).read_bytes()).hexdigest()
        for key, name in names.items()
    }


class ControllerTests(unittest.TestCase):
    def test_status_handles_unreadable_utf8_saved_report(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "orchestration_latest.json").write_bytes(bytes((255, 254)))
            status = SlimeController(data_dir=directory).status()
            self.assertFalse(status["plan_available"])
            self.assertFalse(status["gameplay_ready"])
            self.assertFalse(status["tap_enabled"])

    def test_initial_status_is_plan_only_and_not_ready(self):
        with tempfile.TemporaryDirectory() as directory:
            controller = SlimeController(data_dir=directory)
            status = controller.status()

        self.assertEqual(status["mode"], "PLAN_ONLY")
        self.assertFalse(status["gameplay_ready"])
        self.assertFalse(status["tap_enabled"])
        self.assertFalse(status["touch_injection"])

    def test_tap_is_always_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            result = SlimeController(data_dir=directory).execute("TAP")

        self.assertFalse(result["accepted"])
        self.assertFalse(result["touch_events_sent"])
        self.assertFalse(result["live_execution_allowed"])

    def test_paused_controller_does_not_run_planner(self):
        with tempfile.TemporaryDirectory() as directory:
            controller = SlimeController(data_dir=directory)
            controller.execute("PAUSE")
            with patch("orchestration.run_orchestration") as run:
                result = controller.execute("PLAN")

        self.assertFalse(result["accepted"])
        run.assert_not_called()

    def test_plan_delegates_to_orchestration_without_live_actions(self):
        fake_report = {
            "planner": {"recommended_group": ["A", "B"]},
            "decision": "BLOCKED_NO_VERIFIED_PLAN",
            "evidence": {"evidence_gate_passed": False},
            "game_taps_enabled": False,
            "live_execution_allowed": False,
            "actions_performed": False,
            "shooter_observation_quality": {
                "colour_independently_verified": False,
                "ammunition_independently_verified": False,
                "slot_mapping_independently_verified": False,
                "interpretation": "Simulation only; detector values are unverified.",
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            write_capture_pair(directory)
            controller = SlimeController(data_dir=directory)
            with patch(
                "orchestration.run_orchestration",
                return_value=fake_report,
            ) as run:
                result = controller.execute("PLAN")

        self.assertTrue(result["accepted"])
        self.assertFalse(result["plan_available"])
        self.assertFalse(result["plan_is_simulation_candidate"])
        self.assertIs(result["plan_is_gameplay_verified"], False)
        self.assertEqual(
            result["plan_verification_status"], "NO_VERIFIED_PLAN"
        )
        self.assertIs(
            result["shooter_observation_quality"][
                "ammunition_independently_verified"
            ],
            False,
        )
        self.assertIsNone(result["recommended_group"])
        self.assertFalse(result["evidence_gate_passed"])
        self.assertFalse(result["touch_events_sent"])
        self.assertFalse(result["live_execution_allowed"])
        run.assert_called_once()

    def test_plan_blocks_when_capture_files_are_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            controller = SlimeController(data_dir=directory)
            with patch("orchestration.run_orchestration") as run:
                result = controller.execute("PLAN")
        self.assertFalse(result["accepted"])
        self.assertIn("fresh screenshot capture is required", result["reason"])
        run.assert_not_called()


    def test_plan_blocks_when_source_pixel_audit_is_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            write_capture_pair(directory)
            (Path(directory) / "source_pixel_audit_latest.json").unlink()
            controller = SlimeController(data_dir=directory)
            with patch("orchestration.run_orchestration") as run:
                result = controller.execute("PLAN")
        self.assertFalse(result["accepted"])
        self.assertIn("pixel audit is missing", result["reason"])
        run.assert_not_called()

    def test_plan_blocks_stale_capture_before_orchestration(self):
        stale = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
        with tempfile.TemporaryDirectory() as directory:
            write_capture_pair(directory, captured_at=stale)
            controller = SlimeController(data_dir=directory)
            with patch("orchestration.run_orchestration") as run:
                result = controller.execute("PLAN")
        self.assertFalse(result["accepted"])
        self.assertIn("stale", result["reason"])
        run.assert_not_called()

    def test_plan_blocks_board_shooter_hash_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            write_capture_pair(directory, shooter_hash="b" * 64)
            controller = SlimeController(data_dir=directory)
            with patch("orchestration.run_orchestration") as run:
                result = controller.execute("PLAN")
        self.assertFalse(result["accepted"])
        self.assertIn("screenshot hash", result["reason"])
        run.assert_not_called()

    def test_controller_hides_candidate_when_evidence_gate_fails(self):
        fake_report = {
            "planner": {"recommended_group": ["A"]},
            "decision": "BLOCKED_NO_VERIFIED_PLAN",
            "evidence": {"evidence_gate_passed": False},
        }
        with tempfile.TemporaryDirectory() as directory:
            write_capture_pair(directory)
            controller = SlimeController(data_dir=directory)
            with patch(
                "orchestration.run_orchestration",
                return_value=fake_report,
            ):
                result = controller.execute("PLAN")
        self.assertFalse(result["plan_available"])
        self.assertIsNone(result["recommended_group"])
        self.assertFalse(result["evidence_gate_passed"])

    def test_no_candidate_is_reported_as_no_plan(self):
        fake_report = {
            "planner": {"recommended_group": None},
            "decision": "BLOCKED_NO_VERIFIED_PLAN",
            "evidence": {"evidence_gate_passed": False},
        }
        with tempfile.TemporaryDirectory() as directory:
            write_capture_pair(directory)
            controller = SlimeController(data_dir=directory)
            with patch(
                "orchestration.run_orchestration",
                return_value=fake_report,
            ):
                result = controller.execute("PLAN")

        self.assertTrue(result["accepted"])
        self.assertFalse(result["plan_available"])
        self.assertIsNone(result["recommended_group"])

    def test_status_never_promotes_external_readiness_flags(self):
        with tempfile.TemporaryDirectory() as directory:
            report_path = Path(directory) / "orchestration_latest.json"
            report_path.write_text(json.dumps({
                "gameplay_ready": True,
                "game_taps_enabled": True,
                "decision": "VERIFIED_PLAN_AVAILABLE_BUT_LIVE_ACTIONS_DISABLED",
                "plan_verification_status": "GAMEPLAY_VERIFIED",
                "shooter_observation_quality": {
                    "colour_independently_verified": True,
                    "ammunition_independently_verified": True,
                    "slot_mapping_independently_verified": True,
                },
                "evidence": {"evidence_gate_passed": True},
                "planner": {"recommended_group": ["A"]},
            }))
            status = SlimeController(data_dir=directory).status()

        self.assertFalse(status["gameplay_ready"])
        self.assertFalse(status["tap_enabled"])
        self.assertFalse(status["touch_injection"])
        self.assertFalse(status["plan_available"])
        self.assertFalse(status["capture_evidence_valid"])
        self.assertFalse(status["capture_report_matches_current_capture"])
        self.assertFalse(status["plan_is_gameplay_verified"])
        self.assertEqual(status["plan_verification_status"], "NO_VERIFIED_PLAN")
        self.assertFalse(
            status["shooter_observation_quality"][
                "colour_independently_verified"
            ]
        )
        self.assertFalse(
            status["shooter_observation_quality"][
                "ammunition_independently_verified"
            ]
        )
        self.assertFalse(
            status["shooter_observation_quality"][
                "slot_mapping_independently_verified"
            ]
        )

    def test_status_requires_current_capture_before_showing_saved_plan(self):
        report = {
            "decision": "VERIFIED_PLAN_AVAILABLE_BUT_LIVE_ACTIONS_DISABLED",
            "plan_verification_status": (
                "SIMULATION_CANDIDATE_ONLY_NOT_GAMEPLAY_VERIFIED"
            ),
            "shooter_observation_quality": {
                "colour_independently_verified": False,
                "ammunition_independently_verified": False,
                "slot_mapping_independently_verified": False,
                "interpretation": "Simulation only; detector values are unverified.",
            },
            "evidence": {"evidence_gate_passed": True},
            "planner": {"recommended_group": ["A"]},
            "capture_provenance": {
                "source_sha256": "a" * 64,
                "capture_session_id": "session-abc",
                "captured_at": "PLACEHOLDER",
                "snapshot_id": "sha256:" + "a" * 64,
                "board_snapshot_id": "sha256:" + "a" * 64,
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            write_capture_pair(directory)
            report["capture_bundle_file_sha256"] = capture_bundle_hashes(directory)
            report["planning_evidence_file_sha256"] = planning_evidence_hashes(directory)
            board = json.loads((Path(directory) / "board_observation_latest.json").read_text())
            report["capture_provenance"]["captured_at"] = board["captured_at"]
            report_path = Path(directory) / "orchestration_latest.json"
            report_path.write_text(json.dumps(report))
            status = SlimeController(data_dir=directory).status()
        self.assertTrue(status["capture_evidence_valid"])
        self.assertTrue(status["capture_report_matches_current_capture"])
        self.assertTrue(status["plan_available"])
        self.assertTrue(status["plan_is_simulation_candidate"])
        self.assertIs(status["plan_is_gameplay_verified"], False)
        self.assertEqual(
            status["plan_verification_status"],
            "SIMULATION_CANDIDATE_ONLY_NOT_GAMEPLAY_VERIFIED",
        )
        self.assertIs(
            status["shooter_observation_quality"][
                "colour_independently_verified"
            ],
            False,
        )
        self.assertFalse(status["gameplay_ready"])
        self.assertFalse(status["tap_enabled"])

    def test_status_hides_plan_when_board_calibration_fingerprint_is_stale(self):
        report = {
            "decision": "VERIFIED_PLAN_AVAILABLE_BUT_LIVE_ACTIONS_DISABLED",
            "evidence": {"evidence_gate_passed": True},
            "planner": {"recommended_group": ["A"]},
            "capture_provenance": {
                "source_sha256": "a" * 64,
                "capture_session_id": "session-abc",
                "captured_at": "PLACEHOLDER",
                "snapshot_id": "sha256:" + "a" * 64,
                "board_snapshot_id": "sha256:" + "a" * 64,
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            write_capture_pair(directory)
            board_path = Path(directory) / "board_observation_latest.json"
            board = json.loads(board_path.read_text())
            report["capture_provenance"]["captured_at"] = board["captured_at"]
            # Model an older saved plan whose artifact hashes match its board
            # file, but whose board calibration fingerprint no longer matches
            # the currently pinned calibration input.
            board["calibration_sha256"] = "f" * 64
            board_path.write_text(json.dumps(board))
            report["capture_bundle_file_sha256"] = capture_bundle_hashes(directory)
            report["planning_evidence_file_sha256"] = planning_evidence_hashes(directory)
            (Path(directory) / "orchestration_latest.json").write_text(
                json.dumps(report)
            )
            status = SlimeController(data_dir=directory).status()

        self.assertTrue(status["capture_evidence_valid"])
        self.assertTrue(status["planning_evidence_matches_current_files"])
        self.assertFalse(status["board_calibration_matches_current_config"])
        self.assertFalse(status["capture_report_matches_current_capture"])
        self.assertFalse(status["plan_available"])

    def test_status_uses_same_capture_object_after_source_file_replacement(self):
        from orchestration import _read_capture_bundle as read_bundle

        report = {
            "decision": "VERIFIED_PLAN_AVAILABLE_BUT_LIVE_ACTIONS_DISABLED",
            "evidence": {"evidence_gate_passed": True},
            "planner": {"recommended_group": ["A"]},
            "capture_provenance": {
                "source_sha256": "a" * 64,
                "capture_session_id": "session-abc",
                "captured_at": "PLACEHOLDER",
                "snapshot_id": "sha256:" + "a" * 64,
                "board_snapshot_id": "sha256:" + "a" * 64,
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            write_capture_pair(directory)
            report["capture_bundle_file_sha256"] = capture_bundle_hashes(directory)
            report["planning_evidence_file_sha256"] = planning_evidence_hashes(directory)
            board_path = Path(directory) / "board_observation_latest.json"
            shooter_path = Path(directory) / "shooter_detection.json"
            board = json.loads(board_path.read_text())
            report["capture_provenance"]["captured_at"] = board["captured_at"]
            (Path(directory) / "orchestration_latest.json").write_text(
                json.dumps(report)
            )

            def read_then_replace(observation, shooters, pixel_audit_path=None):
                pinned = read_bundle(observation, shooters, pixel_audit_path)
                board_path.write_text(json.dumps({
                    "source_sha256": "b" * 64,
                    "capture_session_id": "replaced-session",
                }))
                return pinned

            controller = SlimeController(data_dir=directory)
            with patch(
                "orchestration._read_capture_bundle",
                side_effect=read_then_replace,
            ) as read_once:
                status = controller.status()

            self.assertEqual(read_once.call_count, 1)
            self.assertNotEqual(
                json.loads(board_path.read_text())["source_sha256"],
                report["capture_provenance"]["source_sha256"],
            )
            self.assertTrue(status["capture_evidence_valid"])
            self.assertTrue(status["capture_report_matches_current_capture"])
            self.assertTrue(status["plan_available"])

    def test_status_hides_saved_plan_when_capture_is_stale(self):
        stale = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
        report = {
            "decision": "VERIFIED_PLAN_AVAILABLE_BUT_LIVE_ACTIONS_DISABLED",
            "evidence": {"evidence_gate_passed": True},
            "planner": {"recommended_group": ["A"]},
            "capture_provenance": {
                "source_sha256": "a" * 64,
                "capture_session_id": "session-abc",
                "captured_at": stale,
                "snapshot_id": "sha256:" + "a" * 64,
                "board_snapshot_id": "sha256:" + "a" * 64,
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            write_capture_pair(directory, captured_at=stale)
            report_path = Path(directory) / "orchestration_latest.json"
            report_path.write_text(json.dumps(report))
            status = SlimeController(data_dir=directory).status()
        self.assertFalse(status["capture_evidence_valid"])
        self.assertFalse(status["capture_report_matches_current_capture"])
        self.assertFalse(status["plan_available"])

    def test_status_hides_plan_when_saved_report_belongs_to_previous_capture(self):
        report = {
            "decision": "VERIFIED_PLAN_AVAILABLE_BUT_LIVE_ACTIONS_DISABLED",
            "evidence": {"evidence_gate_passed": True},
            "planner": {"recommended_group": ["A"]},
            "capture_provenance": {
                "source_sha256": "b" * 64,
                "capture_session_id": "old-session",
                "captured_at": "2026-11-24T10:00:00+00:00",
                "snapshot_id": "sha256:" + "b" * 64,
                "board_snapshot_id": "sha256:" + "b" * 64,
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            write_capture_pair(directory)
            report_path = Path(directory) / "orchestration_latest.json"
            report_path.write_text(json.dumps(report))
            status = SlimeController(data_dir=directory).status()
        self.assertTrue(status["capture_evidence_valid"])
        self.assertFalse(status["capture_report_matches_current_capture"])
        self.assertFalse(status["plan_available"])

    def test_unknown_command_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            result = SlimeController(data_dir=directory).execute("DELETE")

        self.assertFalse(result["accepted"])
        self.assertFalse(result["touch_events_sent"])



    def test_status_hides_saved_plan_when_capture_artifact_changes_without_identity_change(self):
        report = {
            "decision": "VERIFIED_PLAN_AVAILABLE_BUT_LIVE_ACTIONS_DISABLED",
            "evidence": {"evidence_gate_passed": True},
            "planner": {"recommended_group": ["A"]},
            "capture_provenance": {
                "source_sha256": "a" * 64,
                "capture_session_id": "session-abc",
                "captured_at": "PLACEHOLDER",
                "snapshot_id": "sha256:" + "a" * 64,
                "board_snapshot_id": "sha256:" + "a" * 64,
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            write_capture_pair(directory)
            board = json.loads((Path(directory) / "board_observation_latest.json").read_text())
            report["capture_provenance"]["captured_at"] = board["captured_at"]
            report["capture_bundle_file_sha256"] = capture_bundle_hashes(directory)
            report["planning_evidence_file_sha256"] = planning_evidence_hashes(directory)
            report_path = Path(directory) / "orchestration_latest.json"
            report_path.write_text(json.dumps(report))

            # Preserve capture identity/provenance but alter shooter payload.
            shooter_path = Path(directory) / "shooter_detection.json"
            shooter = json.loads(shooter_path.read_text())
            shooter["visible_shooters"] = [
                {"id": "changed", "color": "red", "ammo": 99}
            ]
            shooter_path.write_text(json.dumps(shooter))

            status = SlimeController(data_dir=directory).status()

        self.assertTrue(status["capture_evidence_valid"])
        self.assertFalse(status["capture_report_matches_current_capture"])
        self.assertFalse(status["plan_available"])





    def test_status_hides_saved_plan_when_planning_evidence_file_changes(self):
        report = {
            "decision": "VERIFIED_PLAN_AVAILABLE_BUT_LIVE_ACTIONS_DISABLED",
            "evidence": {"evidence_gate_passed": True},
            "planner": {"recommended_group": ["A"]},
            "capture_provenance": {
                "source_sha256": "a" * 64,
                "capture_session_id": "session-abc",
                "captured_at": "PLACEHOLDER",
                "snapshot_id": "sha256:" + "a" * 64,
                "board_snapshot_id": "sha256:" + "a" * 64,
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            write_capture_pair(directory)
            board = json.loads((Path(directory) / "board_observation_latest.json").read_text())
            report["capture_provenance"]["captured_at"] = board["captured_at"]
            report["capture_bundle_file_sha256"] = capture_bundle_hashes(directory)
            report["planning_evidence_file_sha256"] = planning_evidence_hashes(directory)
            report_path = Path(directory) / "orchestration_latest.json"
            report_path.write_text(json.dumps(report))

            # Each upstream geometry/board input must invalidate the saved
            # plan even while capture identity and derived reports are unchanged.
            for name in (
                "vision_level39.json",
                "edge_confidence_latest.json",
                "reachability_audit.json",
                "conveyor_calibration.json",
                "bonded_groups_confirmed.json",
            ):
                with self.subTest(upstream_input=name):
                    path = Path(directory) / name
                    original = path.read_text()
                    path.write_text(json.dumps({"fixture": "modified"}))
                    status = SlimeController(data_dir=directory).status()
                    path.write_text(original)
                    self.assertTrue(status["capture_evidence_valid"])
                    self.assertFalse(status["planning_evidence_matches_current_files"])
                    self.assertFalse(status["plan_available"])



if __name__ == "__main__":
    unittest.main()



if __name__ == "__main__":
    unittest.main()

