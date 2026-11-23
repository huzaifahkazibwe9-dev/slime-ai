import unittest
from game_state import GameState, Shooter
from planner import plan_next_move


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
    state.snapshot_id = "snap-39"
    return state


def make_evidence():
    planning = {
        "level": 39,
        "gameplay_verified": True,
        "actions_performed": False,
        "results": [
            {
                "position_id": "pA", "target_colour": "red",
                "planning_eligible": True, "geometrically_reachable": True,
                "ammunition_available": True, "observed_ammo": 20,
                "exposed_matching_count": 2, "blockers": [],
            },
            {
                "position_id": "pB", "target_colour": "blue",
                "planning_eligible": True, "geometrically_reachable": True,
                "ammunition_available": True, "observed_ammo": 30,
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
        "identity_verified": True,
        "current_snapshot_id": "snap-39",
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
        "synchronised": True,
        "planning_allowed_by_sync": True,
        "board_snapshot_id": "snap-39",
        "observation_board_snapshot_id": "snap-39",
        "checks": sync_checks,
    }

    return planning, identity, candidates, snapshot


def run_plan(evidence):
    return plan_next_move(make_state(), *evidence)


class PlannerEvidenceTests(unittest.TestCase):
    def test_complete_verified_evidence_accepts_group(self):
        self.assertEqual(run_plan(make_evidence()), ("A", "B"))

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
        self.assertIsNone(plan_next_move(state, *make_evidence()))

    def test_loaded_board_snapshot_missing_rejected(self):
        state = make_state()
        del state.snapshot_id
        self.assertIsNone(plan_next_move(state, *make_evidence()))

    def test_snapshot_id_mismatch_rejected(self):
        e = list(make_evidence())
        e[3]["board_snapshot_id"] = "different"
        self.assertIsNone(run_plan(e))

    def test_snapshot_missing_check_rejected(self):
        e = list(make_evidence())
        e[3]["checks"]["same_state_explicitly_confirmed"] = False
        self.assertIsNone(run_plan(e))

    def test_gameplay_unverified_rejected(self):
        e = list(make_evidence())
        e[0]["gameplay_verified"] = False
        self.assertIsNone(run_plan(e))

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


if __name__ == "__main__":
    unittest.main()
