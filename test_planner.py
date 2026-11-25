import unittest
from game_state import GameState, Shooter
from planner import plan_next_move


def current_source_hashes():
    return {
        "vision_calibration_json": "1" * 64,
        "edge_confidence_json": "2" * 64,
        "reachability_audit_json": "3" * 64,
        "reachability_confidence_json": "4" * 64,
        "conveyor_calibration_json": "5" * 64,
        "planning_json": "6" * 64,
        "identity_json": "7" * 64,
        "snapshot_json": "8" * 64,
        "candidate_json": "9" * 64,
        "conveyor_observations_json": "a" * 64,
        "shooter_detection_json": "b" * 64,
        "board_observation_json": "d" * 64,
    }


def current_calibration_sha256():
    return "c" * 64


SNAPSHOT_ID = "sha256:" + "d" * 64


def current_board_observation():
    return {
        "source_sha256": "d" * 64,
        "snapshot_id": SNAPSHOT_ID,
        "board_snapshot_id": SNAPSHOT_ID,
        "capture_session_id": "session-1",
        "calibration_sha256": current_calibration_sha256(),
    }


def make_state():
    state = GameState(
        board=[["red", "blue"], ["green", "red"]],
        level=39,
        shooters={
            "A": Shooter("A", "red", 20, accessible=True, bonded_ids=["B"]),
            "B": Shooter("B", "blue", 30, accessible=True, bonded_ids=["A"]),
            "C": Shooter("C", "green", 10, accessible=False),
        },
    )
    state.snapshot_id = SNAPSHOT_ID
    state.capture_session_id = "session-1"
    state.calibration_sha256 = current_calibration_sha256()
    state.shooter_capture_provenance_verified = True
    return state


def make_evidence():
    source_hashes = current_source_hashes()
    planning = {
        "input_file_sha256": {
            "reachability_confidence_json": source_hashes["reachability_confidence_json"],
            "candidate_json": source_hashes["candidate_json"],
            "conveyor_calibration_json": source_hashes["conveyor_calibration_json"],
        },
        "upstream_source_kind": "screenshot_observation",
        "confidence_source_file_sha256": {
            "reachability_audit_json": source_hashes["reachability_audit_json"],
            "board_observation_json": source_hashes["board_observation_json"],
        },
        "upstream_source_file_sha256": {
            "board_json": source_hashes["board_observation_json"],
            "conveyor_calibration_json": source_hashes["conveyor_calibration_json"],
            "conveyor_observations_json": source_hashes["conveyor_observations_json"],
        },
        "level": 39,
        "planning_evidence_verified": True,
        "gameplay_verified": False,
        "game_taps_enabled": False,
        "actions_performed": False,
        "results": [
            {
                "position_id": "pA", "target_colour": "red",
                "planning_eligible": True, "geometrically_reachable": True,
                "ammunition_available": True,
                "ammunition_evidence_verified": True,
                "observed_ammo": 20,
                "exposed_matching_count": 2, "blockers": [],
            },
            {
                "position_id": "pB", "target_colour": "blue",
                "planning_eligible": True, "geometrically_reachable": True,
                "ammunition_available": True,
                "ammunition_evidence_verified": True,
                "observed_ammo": 30,
                "exposed_matching_count": 3, "blockers": [],
            },
        ],
    }

    identity = {
        "positions_checked": 8,
        "known_shooters": ["A", "B"],
        "timestamps_known": True,
        "identity_verified": True,
        "errors": [],
        "blockers": [],
    }

    candidate_checks = {
        key: True for key in (
            "four_sides_in_expected_order",
            "eight_observations_present",
            "two_candidate_tracks_supported",
            "candidate_pair_is_user_confirmed_bond",
            "timestamps_known",
            "identity_previously_verified",
            "current_snapshot_identified",
        )
    }

    tracks = {}
    for key, shooter, colour, position, ammo in (
        ("red", "A", "red", "pA", 20),
        ("blue", "B", "blue", "pB", 30),
    ):
        tracks[key] = {
            "candidate_shooter": shooter,
            "panel_colour": colour,
            "current_position_id": position,
            "candidate_supported": True,
            "ammo_non_increasing": True,
            "panel_colour_match": True,
            "observed_colour_consistent": True,
            "observations": [
                {"position_id": position, "colour": colour, "ammo": ammo}
            ],
        }

    candidates = {
        "source_file_sha256": {
            "conveyor_calibration_json": source_hashes["conveyor_calibration_json"],
            "conveyor_visual_observations_json": source_hashes["conveyor_observations_json"],
            "shooter_detection_json": source_hashes["shooter_detection_json"],
        },
        "identity_verified": True,
        "current_snapshot_id": SNAPSHOT_ID,
        "checks": candidate_checks,
        "tracks": tracks,
    }

    sync_checks = {
        key: True for key in (
            "board_snapshot_id_present",
            "observation_snapshot_id_present",
            "snapshot_ids_match",
            "board_session_present",
            "observation_session_present",
            "sessions_match",
            "same_state_explicitly_confirmed",
            "board_timestamp_identified",
            "observation_timestamp_identified",
        )
    }

    snapshot = {
        "board_source_kind": "screenshot_observation",
        "source_file_sha256": {
            "board_observation_json": source_hashes["board_observation_json"],
            "conveyor_observations_json": source_hashes["conveyor_observations_json"],
        },
        "synchronised": True,
        "planning_allowed_by_sync": True,
        "board_snapshot_id": SNAPSHOT_ID,
        "observation_board_snapshot_id": SNAPSHOT_ID,
        "checks": sync_checks,
    }

    return planning, identity, candidates, snapshot


def run_plan(
    evidence, state=None, source_hashes=None, calibration_sha256=None,
    identity_audit=None, board_observation=None,
):
    return plan_next_move(
        make_state() if state is None else state,
        *evidence,
        current_source_file_sha256=(
            current_source_hashes() if source_hashes is None else source_hashes
        ),
        current_calibration_sha256=(
            current_calibration_sha256()
            if calibration_sha256 is None else calibration_sha256
        ),
        current_identity_audit=(
            evidence[1] if identity_audit is None else identity_audit
        ),
        current_board_observation=(
            current_board_observation()
            if board_observation is None else board_observation
        ),
    )


class PlannerEvidenceTests(unittest.TestCase):
    def test_missing_current_source_hashes_fail_closed(self):
        self.assertIsNone(plan_next_move(make_state(), *make_evidence()))

    def test_stale_snapshot_source_hash_fails_closed(self):
        evidence = list(make_evidence())
        evidence[3]["source_file_sha256"]["conveyor_observations_json"] = "d" * 64
        self.assertIsNone(run_plan(evidence))

    def test_stale_confidence_source_hash_fails_closed(self):
        evidence = list(make_evidence())
        evidence[0]["confidence_source_file_sha256"]["board_observation_json"] = "e" * 64
        self.assertIsNone(run_plan(evidence))

    def test_stale_reachability_upstream_hash_fails_closed(self):
        evidence = list(make_evidence())
        evidence[0]["upstream_source_file_sha256"]["conveyor_calibration_json"] = "e" * 64
        self.assertIsNone(run_plan(evidence))

    def test_unknown_upstream_source_kind_fails_closed(self):
        evidence = list(make_evidence())
        evidence[0]["upstream_source_kind"] = "unknown"
        self.assertIsNone(run_plan(evidence))

    def test_identity_object_must_match_pinned_identity(self):
        evidence = make_evidence()
        self.assertIsNone(run_plan(
            evidence,
            identity_audit={"identity_verified": True},
        ))

    def test_board_object_must_match_loaded_state_identity(self):
        board = current_board_observation()
        board["snapshot_id"] = "sha256:" + "e" * 64
        self.assertIsNone(run_plan(
            make_evidence(),
            board_observation=board,
        ))

    def test_board_snapshot_digest_shape_is_required(self):
        board = current_board_observation()
        board["source_sha256"] = "not-a-digest"
        self.assertIsNone(run_plan(
            make_evidence(),
            board_observation=board,
        ))

    def test_malformed_current_source_hash_fails_closed(self):
        hashes = current_source_hashes()
        hashes["edge_confidence_json"] = "not-a-sha256"
        self.assertIsNone(run_plan(make_evidence(), source_hashes=hashes))

    def test_stale_board_calibration_hash_fails_closed(self):
        self.assertIsNone(run_plan(
            make_evidence(),
            calibration_sha256="d" * 64,
        ))

    def test_complete_verified_evidence_accepts_group(self):
        self.assertEqual(run_plan(make_evidence()), ("A", "B"))

    def test_unbound_shooter_capture_rejected_even_with_other_verified_evidence(self):
        state = make_state()
        state.shooter_capture_provenance_verified = False
        self.assertIsNone(run_plan(make_evidence(), state=state))

    def test_missing_shooter_capture_provenance_rejected(self):
        state = make_state()
        del state.shooter_capture_provenance_verified
        self.assertIsNone(run_plan(make_evidence(), state=state))

    def test_missing_identity_audit_rejected(self):
        e = list(make_evidence())
        e[1] = None
        self.assertIsNone(run_plan(e))

    def test_identity_flag_false_rejected(self):
        e = list(make_evidence())
        e[1]["identity_verified"] = False
        self.assertIsNone(run_plan(e))

    def test_unknown_timestamps_rejected(self):
        e = list(make_evidence())
        e[1]["timestamps_known"] = False
        self.assertIsNone(run_plan(e))

    def test_identity_blocker_rejected(self):
        e = list(make_evidence())
        e[1]["blockers"] = ["TIMESTAMPS_UNKNOWN"]
        self.assertIsNone(run_plan(e))

    def test_candidate_report_unverified_rejected(self):
        e = list(make_evidence())
        e[2]["identity_verified"] = False
        self.assertIsNone(run_plan(e))

    def test_missing_current_position_rejected(self):
        e = list(make_evidence())
        del e[2]["tracks"]["red"]["current_position_id"]
        self.assertIsNone(run_plan(e))

    def test_duplicate_current_position_rejected(self):
        e = list(make_evidence())
        e[2]["tracks"]["blue"]["current_position_id"] = "pA"
        e[2]["tracks"]["blue"]["observations"][0]["position_id"] = "pA"
        self.assertIsNone(run_plan(e))

    def test_snapshot_not_synchronised_rejected(self):
        e = list(make_evidence())
        e[3]["synchronised"] = False
        self.assertIsNone(run_plan(e))

    def test_loaded_board_snapshot_mismatch_rejected(self):
        state = make_state()
        state.snapshot_id = "different-board"
        self.assertIsNone(run_plan(make_evidence(), state=state))

    def test_loaded_board_snapshot_missing_rejected(self):
        state = make_state()
        del state.snapshot_id
        self.assertIsNone(run_plan(make_evidence(), state=state))

    def test_snapshot_id_mismatch_rejected(self):
        e = list(make_evidence())
        e[3]["board_snapshot_id"] = "different"
        self.assertIsNone(run_plan(e))

    def test_snapshot_missing_check_rejected(self):
        e = list(make_evidence())
        e[3]["checks"]["same_state_explicitly_confirmed"] = False
        self.assertIsNone(run_plan(e))

    def test_unverified_planning_evidence_is_rejected(self):
        e = list(make_evidence())
        e[0]["planning_evidence_verified"] = False
        self.assertIsNone(run_plan(e))

    def test_verified_dry_run_plan_does_not_claim_gameplay(self):
        e = list(make_evidence())
        e[0]["gameplay_verified"] = False
        e[0]["game_taps_enabled"] = False
        self.assertEqual(run_plan(e), ("A", "B"))

    def test_fabricated_legacy_boolean_not_accepted(self):
        self.assertIsNone(plan_next_move(
            make_state(), make_evidence()[0],
            {"pA": "A", "pB": "B"}, True,
        ))

    def test_planning_blocker_rejected(self):
        e = list(make_evidence())
        e[0]["results"][0]["blockers"] = ["BOARD_NOT_SYNCED"]
        self.assertIsNone(run_plan(e))

    def test_ammunition_mismatch_rejected(self):
        e = list(make_evidence())
        e[0]["results"][0]["observed_ammo"] = 19
        self.assertIsNone(run_plan(e))

    def test_boolean_shooter_ammunition_is_rejected(self):
        state = make_state()
        state.shooters["A"].ammo = True
        self.assertTrue(state.validate())
        self.assertIsNone(run_plan(make_evidence(), state=state))

    def test_unverified_ammunition_evidence_rejected(self):
        e = list(make_evidence())
        e[0]["results"][0]["ammunition_evidence_verified"] = False
        self.assertIsNone(run_plan(e))


class ShooterRotationProgressValidationTests(unittest.TestCase):
    def test_rotation_progress_rejects_boolean_and_non_numeric_values(self):
        for value in (True, False, "0.5", None):
            with self.subTest(value=value):
                shooter = Shooter("S", "red", 1, rotation_progress=value)
                self.assertFalse(shooter.valid())

    def test_rotation_progress_rejects_non_finite_values(self):
        for value in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(value=value):
                shooter = Shooter("S", "red", 1, rotation_progress=value)
                self.assertFalse(shooter.valid())

    def test_rotation_progress_accepts_finite_numeric_range(self):
        for value in (0, 0.0, 0.5, 0.999):
            with self.subTest(value=value):
                shooter = Shooter("S", "red", 1, rotation_progress=value)
                self.assertTrue(shooter.valid())

if __name__ == "__main__":
    unittest.main()
