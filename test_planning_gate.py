import unittest

from planning_gate import evaluate_planning


def make_report():
    return {
        "level": 39,
        "board_dimensions": [2, 2],
        "same_board_state_confirmed": False,
        "capture_freshness": {"fresh": False},
        "board_snapshot_id": "sha256:" + "a" * 64,
        "capture_session_id": "capture-1",
        "captured_at": "2026-11-23T10:00:00+00:00",
        "timestamp_identified": True,
        "conveyor_identity_verified": False,
        "gameplay_verified": False,
        "confidence_audit": {
            "game_taps_enabled": False,
            "source_snapshot_id": "sha256:" + "a" * 64,
            "snapshot_match_verified": True,
        },
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


def make_candidate_report(report=None):
    report = report or make_report()
    captured_at = report["captured_at"]
    snapshot_id = report["board_snapshot_id"]
    session_id = report["capture_session_id"]
    def observation(position_id):
        return {
            "position_id": position_id,
            "board_snapshot_id": snapshot_id,
            "capture_session_id": session_id,
            "captured_at": captured_at,
            "timestamp_identified": True,
        }
    return {
        "board_snapshot_id": snapshot_id,
        "capture_session_id": session_id,
        "captured_at": captured_at,
        "timestamp_identified": True,
        "tracks": {
            "white": {
                "board_snapshot_id": snapshot_id,
                "capture_session_id": session_id,
                "captured_at": captured_at,
                "timestamp_identified": True,
                "observations": [
                    observation(position_id) for position_id in
                    ("bottom_1", "right_2", "top_2", "left_1")
                ],
            },
            "blue_cyan": {
                "board_snapshot_id": snapshot_id,
                "capture_session_id": session_id,
                "captured_at": captured_at,
                "timestamp_identified": True,
                "observations": [
                    observation(position_id) for position_id in
                    ("bottom_2", "right_1", "top_1", "left_2")
                ],
            },
        },
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

    def test_stale_capture_timestamps_rejected(self):
        report = make_report()
        report["same_board_state_confirmed"] = True
        report["capture_freshness"] = {"fresh": False}
        result = evaluate_planning(report)
        self.assertIn(
            "CAPTURE_TIMESTAMPS_NOT_FRESH_AND_ALIGNED",
            result["results"][0]["blockers"],
        )
        self.assertFalse(result["results"][0]["planning_eligible"])

    def test_unmatched_confidence_snapshot_rejected(self):
        report = make_report()
        report["confidence_audit"]["source_snapshot_id"] = "different-board"
        result = evaluate_planning(report)
        self.assertIn(
            "CONFIDENCE_BOARD_SNAPSHOT_UNVERIFIED",
            result["results"][0]["blockers"],
        )
        self.assertFalse(result["results"][0]["planning_eligible"])

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
        report["capture_freshness"] = {"fresh": True}
        report["conveyor_identity_verified"] = True
        report["gameplay_verified"] = True
        position = report["results"][0]
        position["observed_ammo"] = 10
        position["identity_verified"] = True
        position["planning_eligible"] = True
        position["ammo_evidence"] = {
            "position_id": "left_2",
            "ammo": 10,
            "capture_session_id": "capture-1",
            "board_snapshot_id": "sha256:" + "a" * 64,
            "observed_at": "2026-11-23T10:00:00+00:00",
            "verified": True,
            "checks": {
                "ammo_is_non_negative_integer": True,
                "position_identity_matches": True,
                "capture_session_present": True,
                "board_snapshot_present": True,
                "observation_timestamp_present": True,
                "explicit_user_confirmation": True,
            },
        }
        scenario = position["scenarios"][0]
        scenario["confidence_eligible"] = True
        scenario["planning_eligible"] = True

        result = evaluate_planning(
            report,
            candidate_report=make_candidate_report(report),
            conveyor_calibration={
                "timing_calibrated_to_game": True,
                "verified_by_user": True,
            },
        )
        self.assertTrue(result["results"][0]["planning_eligible"])
        self.assertEqual(result["counts"]["eligible_scenarios"], 1)
        self.assertTrue(result["planning_evidence_verified"])
        self.assertFalse(result["gameplay_verified"])
        self.assertFalse(result["game_taps_enabled"])

    def test_missing_conveyor_timing_calibration_blocks_otherwise_valid_plan(self):
        report = make_report()
        report["same_board_state_confirmed"] = True
        report["capture_freshness"] = {"fresh": True}
        report["conveyor_identity_verified"] = True
        report["gameplay_verified"] = True
        position = report["results"][0]
        position["observed_ammo"] = 10
        position["identity_verified"] = True
        position["ammo_evidence"] = {
            "position_id": "left_2", "ammo": 10,
            "capture_session_id": "capture-1",
            "board_snapshot_id": report["board_snapshot_id"],
            "observed_at": report["captured_at"],
            "verified": True,
            "checks": {key: True for key in (
                "ammo_is_non_negative_integer", "position_identity_matches",
                "capture_session_present", "board_snapshot_present",
                "observation_timestamp_present", "explicit_user_confirmation",
            )},
        }
        position["scenarios"][0]["confidence_eligible"] = True
        position["scenarios"][0]["planning_eligible"] = True
        result = evaluate_planning(
            report, candidate_report=make_candidate_report(report)
        )
        self.assertFalse(result["results"][0]["planning_eligible"])
        self.assertIn(
            "CONVEYOR_TIMING_NOT_USER_CALIBRATED",
            result["results"][0]["blockers"],
        )
        self.assertFalse(result["conveyor_timing_calibrated"])

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

    def test_forged_boolean_flag_cannot_verify_ammo(self):
        report = make_report()
        position = report["results"][0]
        position["observed_ammo"] = 8
        position["ammunition_evidence_verified"] = True
        position["identity_verified"] = True
        position["planning_eligible"] = True
        report["same_board_state_confirmed"] = True
        report["conveyor_identity_verified"] = True
        report["gameplay_verified"] = True
        scenario = position["scenarios"][0]
        scenario["confidence_eligible"] = True
        scenario["planning_eligible"] = True
        result = evaluate_planning(report)
        self.assertFalse(result["results"][0]["planning_eligible"])
        self.assertIn(
            "AMMUNITION_OBSERVATION_UNVERIFIED",
            result["results"][0]["blockers"],
        )

    def test_ammo_evidence_for_wrong_shooter_is_rejected(self):
        report = make_report()
        position = report["results"][0]
        position["observed_ammo"] = 8
        position["ammo_evidence"] = {
            "position_id": "right_1",
            "ammo": 8,
            "capture_session_id": "capture-1",
            "board_snapshot_id": "board-1",
            "observed_at": "2026-11-23T10:00:00+03:00",
            "verified": True,
            "checks": {key: True for key in (
                "ammo_is_non_negative_integer",
                "position_identity_matches",
                "capture_session_present",
                "board_snapshot_present",
                "observation_timestamp_present",
                "explicit_user_confirmation",
            )},
        }
        result = evaluate_planning(report)
        self.assertFalse(result["results"][0]["ammunition_evidence_verified"])

    def test_ammo_evidence_count_must_match_observation(self):
        report = make_report()
        position = report["results"][0]
        position["observed_ammo"] = 8
        position["ammo_evidence"] = {
            "position_id": "left_2",
            "ammo": 9,
            "capture_session_id": "capture-1",
            "board_snapshot_id": "board-1",
            "observed_at": "2026-11-23T10:00:00+03:00",
            "verified": True,
            "checks": {key: True for key in (
                "ammo_is_non_negative_integer",
                "position_identity_matches",
                "capture_session_present",
                "board_snapshot_present",
                "observation_timestamp_present",
                "explicit_user_confirmation",
            )},
        }
        result = evaluate_planning(report)
        self.assertFalse(result["results"][0]["ammunition_evidence_verified"])

    def test_malformed_board_snapshot_fingerprint_blocks_planning(self):
        report = make_report()
        report["board_snapshot_id"] = "sha256:short"
        result = evaluate_planning(report, candidate_report=make_candidate_report(report))
        self.assertFalse(result["capture_provenance_verified"])
        self.assertFalse(result["candidate_capture_provenance_verified"])

    def test_malformed_capture_session_id_blocks_planning(self):
        report = make_report()
        report["capture_session_id"] = "session id with spaces"
        result = evaluate_planning(report, candidate_report=make_candidate_report(report))
        self.assertFalse(result["capture_provenance_verified"])
        self.assertFalse(result["candidate_capture_provenance_verified"])

    def test_candidate_malformed_session_id_is_rejected(self):
        report = make_report()
        candidates = make_candidate_report(report)
        candidates["capture_session_id"] = "bad session id"
        result = evaluate_planning(report, candidate_report=candidates)
        self.assertFalse(result["candidate_capture_provenance_verified"])

    def test_missing_board_capture_provenance_blocks_planning(self):
        report = make_report()
        report["timestamp_identified"] = False
        result = evaluate_planning(report)
        self.assertFalse(result["capture_provenance_verified"])
        self.assertIn("BOARD_CAPTURE_PROVENANCE_INCOMPLETE", result["results"][0]["blockers"])

    def test_ammo_evidence_cannot_replace_required_checks_with_arbitrary_flags(self):
        report = make_report()
        position = report["results"][0]
        position["observed_ammo"] = 8
        position["ammo_evidence"] = {
            "position_id": "left_2", "ammo": 8,
            "capture_session_id": "capture-1",
            "board_snapshot_id": report["board_snapshot_id"],
            "observed_at": report["captured_at"],
            "verified": True,
            "checks": {f"fake_{index}": True for index in range(6)},
        }
        result = evaluate_planning(report)
        self.assertFalse(result["results"][0]["ammunition_evidence_verified"])

    def test_malformed_ammo_evidence_session_id_is_rejected(self):
        report = make_report()
        position = report["results"][0]
        position["observed_ammo"] = 8
        position["ammo_evidence"] = {
            "position_id": "left_2", "ammo": 8,
            "capture_session_id": "invalid session",
            "board_snapshot_id": report["board_snapshot_id"],
            "observed_at": report["captured_at"],
            "verified": True,
            "checks": {key: True for key in (
                "ammo_is_non_negative_integer", "position_identity_matches",
                "capture_session_present", "board_snapshot_present",
                "observation_timestamp_present", "explicit_user_confirmation",
            )},
        }
        result = evaluate_planning(report)
        self.assertFalse(result["results"][0]["ammunition_evidence_verified"])

    def test_naive_ammo_timestamp_is_rejected(self):
        report = make_report()
        report["same_board_state_confirmed"] = True
        report["capture_freshness"] = {"fresh": True}
        report["conveyor_identity_verified"] = True
        report["gameplay_verified"] = True
        position = report["results"][0]
        position["observed_ammo"] = 10
        position["identity_verified"] = True
        position["planning_eligible"] = True
        position["ammo_evidence"] = {
            "position_id": "left_2", "ammo": 10,
            "capture_session_id": "capture-1",
            "board_snapshot_id": report["board_snapshot_id"],
            "observed_at": "2026-11-23T10:00:00",
            "verified": True,
            "checks": {key: True for key in (
                "ammo_is_non_negative_integer", "position_identity_matches",
                "capture_session_present", "board_snapshot_present",
                "observation_timestamp_present", "explicit_user_confirmation",
            )},
        }
        scenario = position["scenarios"][0]
        scenario["confidence_eligible"] = True
        scenario["planning_eligible"] = True
        result = evaluate_planning(report)
        self.assertFalse(result["results"][0]["ammunition_evidence_verified"])

    def test_ammo_timestamp_outside_capture_skew_is_rejected(self):
        report = make_report()
        report["same_board_state_confirmed"] = True
        report["capture_freshness"] = {"fresh": True}
        report["conveyor_identity_verified"] = True
        report["gameplay_verified"] = True
        position = report["results"][0]
        position["observed_ammo"] = 10
        position["identity_verified"] = True
        position["planning_eligible"] = True
        position["ammo_evidence"] = {
            "position_id": "left_2", "ammo": 10,
            "capture_session_id": "capture-1",
            "board_snapshot_id": report["board_snapshot_id"],
            "observed_at": "2026-11-23T10:03:00+00:00",
            "verified": True,
            "checks": {key: True for key in (
                "ammo_is_non_negative_integer", "position_identity_matches",
                "capture_session_present", "board_snapshot_present",
                "observation_timestamp_present", "explicit_user_confirmation",
            )},
        }
        scenario = position["scenarios"][0]
        scenario["confidence_eligible"] = True
        scenario["planning_eligible"] = True
        result = evaluate_planning(report)
        self.assertFalse(result["results"][0]["ammunition_evidence_verified"])
    def test_missing_candidate_report_blocks_planning(self):
        report = make_report()
        result = evaluate_planning(report)
        self.assertFalse(result["candidate_capture_provenance_verified"])
        self.assertIn(
            "CANDIDATE_CAPTURE_PROVENANCE_UNVERIFIED",
            result["results"][0]["blockers"],
        )

    def test_candidate_track_from_different_snapshot_is_rejected(self):
        report = make_report()
        candidates = make_candidate_report(report)
        candidates["tracks"]["white"]["board_snapshot_id"] = "sha256:" + "b" * 64
        result = evaluate_planning(report, candidate_report=candidates)
        self.assertFalse(result["candidate_capture_provenance_verified"])

    def test_candidate_observation_with_stale_timestamp_is_rejected(self):
        report = make_report()
        candidates = make_candidate_report(report)
        candidates["tracks"]["white"]["observations"][0]["captured_at"] = (
            "2026-11-23T09:55:00+00:00"
        )
        result = evaluate_planning(report, candidate_report=candidates)
        self.assertFalse(result["candidate_capture_provenance_verified"])

    def test_candidate_track_missing_observation_is_rejected(self):
        report = make_report()
        candidates = make_candidate_report(report)
        candidates["tracks"]["white"]["observations"].pop()
        result = evaluate_planning(report, candidate_report=candidates)
        self.assertFalse(result["candidate_capture_provenance_verified"])

    def test_duplicate_candidate_observation_position_is_rejected(self):
        report = make_report()
        candidates = make_candidate_report(report)
        candidates["tracks"]["white"]["observations"] = [
            {
                "position_id": "bottom_1",
                "board_snapshot_id": report["board_snapshot_id"],
                "capture_session_id": report["capture_session_id"],
                "captured_at": report["captured_at"],
                "timestamp_identified": True,
            }
            for _ in range(4)
        ]
        result = evaluate_planning(report, candidate_report=candidates)
        self.assertFalse(result["candidate_capture_provenance_verified"])

    def test_candidate_track_timestamp_must_align_with_report_timestamp(self):
        report = make_report()
        candidates = make_candidate_report(report)
        candidates["captured_at"] = "2026-11-23T09:59:00+00:00"
        candidates["tracks"]["white"]["captured_at"] = (
            "2026-11-23T10:01:01+00:00"
        )
        result = evaluate_planning(report, candidate_report=candidates)
        self.assertFalse(result["candidate_capture_provenance_verified"])

    def test_candidate_observation_timestamp_must_align_with_track(self):
        report = make_report()
        candidates = make_candidate_report(report)
        candidates["tracks"]["blue_cyan"]["observations"][0]["captured_at"] = (
            "2026-11-23T10:02:01+00:00"
        )
        result = evaluate_planning(report, candidate_report=candidates)
        self.assertFalse(result["candidate_capture_provenance_verified"])

    def test_candidate_track_without_identified_timestamp_is_rejected(self):
        report = make_report()
        candidates = make_candidate_report(report)
        candidates["tracks"]["blue_cyan"]["timestamp_identified"] = False
        result = evaluate_planning(report, candidate_report=candidates)
        self.assertFalse(result["candidate_capture_provenance_verified"])

    def test_decision_contains_exact_board_and_shooter_evidence_trace(self):
        report = make_report()
        position = report["results"][0]
        position["observed_ammo"] = 7
        position["ammo_evidence"] = {
            "position_id": "left_2",
            "ammo": 7,
            "board_snapshot_id": report["board_snapshot_id"],
            "capture_session_id": report["capture_session_id"],
            "observed_at": report["captured_at"],
            "verified": True,
            "checks": {key: True for key in (
                "ammo_is_non_negative_integer", "position_identity_matches",
                "capture_session_present", "board_snapshot_present",
                "observation_timestamp_present", "explicit_user_confirmation",
            )},
        }
        result = evaluate_planning(
            report, candidate_report=make_candidate_report(report)
        )
        trace = result["results"][0]["evidence_trace"]
        self.assertEqual(
            trace["board_capture"]["board_snapshot_id"],
            report["board_snapshot_id"],
        )
        self.assertEqual(
            trace["board_capture"]["capture_session_id"],
            report["capture_session_id"],
        )
        self.assertEqual(trace["shooter_observation"]["position_id"], "left_2")
        self.assertEqual(trace["shooter_observation"]["ammo"], 7)
        self.assertTrue(trace["shooter_observation"]["verified"])
        self.assertTrue(trace["candidate_capture_provenance_verified"])

    def test_missing_ammo_evidence_remains_visible_in_decision_trace(self):
        result = evaluate_planning(make_report())
        trace = result["results"][0]["evidence_trace"]
        self.assertEqual(trace["board_capture"]["board_snapshot_id"],
                         make_report()["board_snapshot_id"])
        self.assertIsNone(trace["shooter_observation"]["position_id"])
        self.assertFalse(trace["shooter_observation"]["verified"])
        self.assertFalse(trace["candidate_capture_provenance_verified"])

    def test_safety_flags_always_disabled(self):
        result = evaluate_planning(make_report())
        self.assertFalse(result["planning_evidence_verified"])
        self.assertFalse(result["gameplay_verified"])
        self.assertFalse(result["game_taps_enabled"])
        self.assertFalse(result["actions_performed"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
