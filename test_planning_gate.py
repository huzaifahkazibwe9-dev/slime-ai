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
    observation = {
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
                "observations": [dict(observation)],
            },
            "blue_cyan": {
                "board_snapshot_id": snapshot_id,
                "capture_session_id": session_id,
                "captured_at": captured_at,
                "timestamp_identified": True,
                "observations": [dict(observation)],
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

        result = evaluate_planning(report, candidate_report=make_candidate_report(report))
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

    def test_missing_board_capture_provenance_blocks_planning(self):
        report = make_report()
        report["timestamp_identified"] = False
        result = evaluate_planning(report)
        self.assertFalse(result["capture_provenance_verified"])
        self.assertIn("BOARD_CAPTURE_PROVENANCE_INCOMPLETE", result["results"][0]["blockers"])

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

    def test_candidate_track_without_identified_timestamp_is_rejected(self):
        report = make_report()
        candidates = make_candidate_report(report)
        candidates["tracks"]["blue_cyan"]["timestamp_identified"] = False
        result = evaluate_planning(report, candidate_report=candidates)
        self.assertFalse(result["candidate_capture_provenance_verified"])

    def test_safety_flags_always_disabled(self):
        result = evaluate_planning(make_report())
        self.assertFalse(result["gameplay_verified"])
        self.assertFalse(result["game_taps_enabled"])
        self.assertFalse(result["actions_performed"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
