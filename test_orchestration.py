import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

from game_state import GameState
from orchestration import (
    evidence_status,
    resolve_candidate_report_path,
    run_multi_batch_diagnostic,
)
import multi_batch_candidate_planner


class OrchestrationTests(unittest.TestCase):
    def test_canonical_candidate_artifact_precedes_legacy_reports(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            legacy = root / "candidate_tracking_latest.json"
            canonical = root / "conveyor_identity_candidates.json"
            legacy.write_text("{}")
            canonical.write_text("{}")

            selected, source = resolve_candidate_report_path(root)

            self.assertEqual(selected, canonical)
            self.assertEqual(source, "canonical")

    def test_explicit_candidate_report_path_is_never_overridden(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            canonical = root / "conveyor_identity_candidates.json"
            explicit = root / "custom_candidates.json"
            canonical.write_text("{}")
            explicit.write_text("{}")

            selected, source = resolve_candidate_report_path(
                root, explicit_path=explicit
            )

            self.assertEqual(selected, explicit)
            self.assertEqual(source, "explicit")

    def test_legacy_candidate_artifact_is_fallback_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            legacy = root / "candidate_tracks_latest.json"
            legacy.write_text("{}")

            selected, source = resolve_candidate_report_path(root)

            self.assertEqual(selected, legacy)
            self.assertEqual(source, "legacy_fallback")

    def test_missing_candidate_artifact_fails_closed_to_canonical_path(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            selected, source = resolve_candidate_report_path(root)

            self.assertEqual(
                selected, root / "conveyor_identity_candidates.json"
            )
            self.assertEqual(source, "missing")

    def test_missing_evidence_blocks(self):
        result = evidence_status(None, None, None, None)
        self.assertFalse(result["evidence_gate_passed"])

    def test_current_unverified_evidence_blocks(self):
        planning = {
            "decision": "NO_VERIFIED_PLANNING_CANDIDATES",
            "gameplay_verified": False,
            "actions_performed": False,
        }
        identity = {
            "identity_verified": False,
            "timestamps_known": False,
            "errors": [],
            "blockers": ["unknown"],
        }
        snapshot = {
            "synchronised": False,
            "planning_allowed_by_sync": False,
        }
        candidates = {"identity_verified": False}
        result = evidence_status(planning, identity, snapshot, candidates)
        self.assertFalse(result["evidence_gate_passed"])

    def test_all_evidence_checks_required(self):
        planning = {
            "decision": "ELIGIBLE_CANDIDATES_FOUND",
            "gameplay_verified": True,
            "actions_performed": False,
            "capture_freshness_verified": True,
            "candidate_capture_provenance_verified": True,
            "board_snapshot_id": "sha256:" + "a" * 64,
            "capture_session_id": "session-1",
            "captured_at": "2026-11-23T10:00:30+00:00",
            "timestamp_identified": True,
        }
        identity = {
            "identity_verified": True,
            "timestamps_known": True,
            "snapshot_linked": True,
            "board_snapshot_id": "sha256:" + "a" * 64,
            "capture_session_linked": True,
            "capture_session_id": "session-1",
            "captured_at": "2026-11-23T10:00:00+00:00",
            "timestamp_identified": True,
            "errors": [],
            "blockers": [],
        }
        snapshot = {
            "synchronised": True,
            "planning_allowed_by_sync": True,
            "board_snapshot_id": "sha256:" + "a" * 64,
            "capture_session_id": "session-1",
            "captured_at": "2026-11-23T10:00:00+00:00",
            "timestamp_identified": True,
            "bundle_synchronisation": {
                "synchronised": True,
                "planning_allowed_by_sync": True,
            },
        }
        candidates = {
            "identity_verified": True, "candidate_provenance_verified": True,
            "board_snapshot_id": "sha256:" + "a" * 64,
            "capture_session_id": "session-1",
            "captured_at": "2026-11-23T10:01:00+00:00",
            "timestamp_identified": True,
        }
        result = evidence_status(planning, identity, snapshot, candidates)
        self.assertTrue(result["evidence_gate_passed"])
        self.assertTrue(result["checks"]["planning_capture_freshness_verified"])
        self.assertTrue(result["checks"]["all_evidence_sources_share_capture"])

    def test_missing_planning_freshness_blocks_otherwise_valid_evidence(self):
        planning = {
            "decision": "ELIGIBLE_CANDIDATES_FOUND",
            "gameplay_verified": True,
            "actions_performed": False,
        }
        identity = {
            "identity_verified": True,
            "timestamps_known": True,
            "snapshot_linked": True,
            "board_snapshot_id": "sha256:" + "a" * 64,
            "capture_session_linked": True,
            "capture_session_id": "session-1",
            "captured_at": "2026-11-23T10:00:00+00:00",
            "timestamp_identified": True,
            "errors": [],
            "blockers": [],
        }
        snapshot = {
            "synchronised": True,
            "planning_allowed_by_sync": True,
            "bundle_synchronisation": {
                "synchronised": True,
                "planning_allowed_by_sync": True,
            },
        }
        candidates = {"identity_verified": True, "candidate_provenance_verified": True}
        result = evidence_status(planning, identity, snapshot, candidates)
        self.assertFalse(result["evidence_gate_passed"])
        self.assertFalse(result["checks"]["planning_capture_freshness_verified"])

    def test_missing_bundle_sync_blocks_even_if_legacy_snapshot_passes(self):
        planning = {
            "decision": "ELIGIBLE_CANDIDATES_FOUND",
            "gameplay_verified": True,
            "actions_performed": False,
        }
        identity = {
            "identity_verified": True,
            "timestamps_known": True,
            "snapshot_linked": True,
            "board_snapshot_id": "sha256:" + "a" * 64,
            "capture_session_linked": True,
            "capture_session_id": "session-1",
            "captured_at": "2026-11-23T10:00:00+00:00",
            "timestamp_identified": True,
            "errors": [],
            "blockers": [],
        }
        snapshot = {
            "synchronised": True,
            "planning_allowed_by_sync": True,
        }
        candidates = {"identity_verified": True, "candidate_provenance_verified": True}
        result = evidence_status(planning, identity, snapshot, candidates)
        self.assertFalse(result["evidence_gate_passed"])
        self.assertFalse(result["checks"]["evidence_bundle_synchronised"])

    def test_bundle_sync_mismatch_blocks_planning(self):
        planning = {
            "decision": "ELIGIBLE_CANDIDATES_FOUND",
            "gameplay_verified": True,
            "actions_performed": False,
        }
        identity = {
            "identity_verified": True,
            "timestamps_known": True,
            "snapshot_linked": True,
            "board_snapshot_id": "sha256:" + "a" * 64,
            "capture_session_linked": True,
            "capture_session_id": "session-1",
            "captured_at": "2026-11-23T10:00:00+00:00",
            "timestamp_identified": True,
            "errors": [],
            "blockers": [],
        }
        snapshot = {
            "synchronised": True,
            "planning_allowed_by_sync": True,
            "bundle_synchronisation": {
                "synchronised": False,
                "planning_allowed_by_sync": False,
            },
        }
        candidates = {"identity_verified": True, "candidate_provenance_verified": True}
        result = evidence_status(planning, identity, snapshot, candidates)
        self.assertFalse(result["evidence_gate_passed"])

    def test_identity_without_explicit_capture_provenance_blocks(self):
        identity = {
            "identity_verified": True,
            "timestamps_known": True,
            "errors": [],
            "blockers": [],
            "snapshot_linked": False,
            "capture_session_linked": False,
        }
        planning = {
            "decision": "ELIGIBLE_CANDIDATES_FOUND",
            "gameplay_verified": True,
            "actions_performed": False,
            "capture_freshness_verified": True,
            "candidate_capture_provenance_verified": True,
        }
        snapshot = {
            "synchronised": True,
            "planning_allowed_by_sync": True,
            "bundle_synchronisation": {
                "synchronised": True,
                "planning_allowed_by_sync": True,
            },
        }
        candidates = {"identity_verified": True, "candidate_provenance_verified": True}
        result = evidence_status(planning, identity, snapshot, candidates)
        self.assertFalse(result["evidence_gate_passed"])
        self.assertFalse(
            result["checks"]["identity_snapshot_provenance_complete"]
        )
        self.assertFalse(
            result["checks"]["identity_capture_session_provenance_complete"]
        )

    def test_missing_candidate_capture_provenance_blocks(self):
        result = evidence_status(
            {
                "decision": "ELIGIBLE_CANDIDATES_FOUND",
                "gameplay_verified": True,
                "actions_performed": False,
                "capture_freshness_verified": True,
            "candidate_capture_provenance_verified": True,
            },
            {
                "identity_verified": True,
                "timestamps_known": True,
                "snapshot_linked": True,
                "board_snapshot_id": "sha256:" + "a" * 64,
                "capture_session_linked": True,
                "capture_session_id": "session-1",
                "captured_at": "2026-11-23T10:00:00+00:00",
                "timestamp_identified": True,
                "errors": [],
                "blockers": [],
            },
            {
                "synchronised": True,
                "planning_allowed_by_sync": True,
                "bundle_synchronisation": {
                    "synchronised": True,
                    "planning_allowed_by_sync": True,
                },
            },
            {"identity_verified": True},
        )
        self.assertFalse(result["evidence_gate_passed"])
        self.assertFalse(result["checks"]["candidate_capture_provenance_verified"])

    def test_malformed_snapshot_fingerprint_blocks_identity_provenance(self):
        result = evidence_status(
            {}, {
                "snapshot_linked": True,
                "board_snapshot_id": "sha256:short",
            }, {}, {}
        )
        self.assertFalse(
            result["checks"]["identity_snapshot_provenance_complete"]
        )

    def test_naive_identity_timestamp_blocks_capture_provenance(self):
        result = evidence_status(
            {}, {
                "capture_session_linked": True,
                "capture_session_id": "session-1",
                "timestamp_identified": True,
                "captured_at": "2026-11-23T10:00:00",
            }, {}, {}
        )
        self.assertFalse(
            result["checks"]["identity_capture_session_provenance_complete"]
        )

    def test_malformed_identity_session_id_blocks_capture_provenance(self):
        result = evidence_status(
            {}, {
                "capture_session_linked": True,
                "capture_session_id": "invalid session id",
                "timestamp_identified": True,
                "captured_at": "2026-11-23T10:00:00+03:00",
            }, {}, {}
        )
        self.assertFalse(
            result["checks"]["identity_capture_session_provenance_complete"]
        )


    def test_cross_source_fingerprint_mismatch_blocks(self):
        fp = "sha256:" + "a" * 64
        common = {"capture_session_id": "session-1", "timestamp_identified": True}
        planning = dict(common, board_snapshot_id="sha256:" + "b" * 64,
                        captured_at="2026-11-23T10:00:00+00:00",
                        decision="ELIGIBLE_CANDIDATES_FOUND", gameplay_verified=True,
                        actions_performed=False, capture_freshness_verified=True,
                        candidate_capture_provenance_verified=True)
        identity = dict(common, board_snapshot_id=fp,
                        captured_at="2026-11-23T10:00:00+00:00",
                        identity_verified=True, timestamps_known=True,
                        snapshot_linked=True, capture_session_linked=True,
                        errors=[], blockers=[])
        snapshot = dict(common, board_snapshot_id=fp,
                        captured_at="2026-11-23T10:00:00+00:00",
                        synchronised=True, planning_allowed_by_sync=True,
                        bundle_synchronisation={"synchronised": True, "planning_allowed_by_sync": True})
        candidates = dict(common, board_snapshot_id=fp,
                          captured_at="2026-11-23T10:00:00+00:00",
                          identity_verified=True, candidate_provenance_verified=True)
        result = evidence_status(planning, identity, snapshot, candidates)
        self.assertFalse(result["checks"]["all_evidence_sources_share_capture"])
        self.assertFalse(result["evidence_gate_passed"])

    def test_cross_source_timestamp_skew_blocks(self):
        fp = "sha256:" + "a" * 64
        common = {"board_snapshot_id": fp, "capture_session_id": "session-1",
                  "timestamp_identified": True}
        planning = dict(common, captured_at="2026-11-23T10:00:00+00:00",
                        decision="ELIGIBLE_CANDIDATES_FOUND", gameplay_verified=True,
                        actions_performed=False, capture_freshness_verified=True,
                        candidate_capture_provenance_verified=True)
        identity = dict(common, captured_at="2026-11-23T10:00:00+00:00",
                        identity_verified=True, timestamps_known=True,
                        snapshot_linked=True, capture_session_linked=True,
                        errors=[], blockers=[])
        snapshot = dict(common, captured_at="2026-11-23T10:03:00+00:00",
                        synchronised=True, planning_allowed_by_sync=True,
                        bundle_synchronisation={"synchronised": True, "planning_allowed_by_sync": True})
        candidates = dict(common, captured_at="2026-11-23T10:00:00+00:00",
                          identity_verified=True, candidate_provenance_verified=True)
        result = evidence_status(planning, identity, snapshot, candidates)
        self.assertFalse(result["checks"]["all_evidence_sources_share_capture"])

    def test_live_actions_always_disabled(self):
        result = evidence_status({}, {}, {}, {})
        self.assertIs(result["game_taps_enabled"], False)
        self.assertIs(result["actions_performed"], False)


    def test_multi_batch_diagnostic_returns_compact_plan_summary(self):
        state = GameState([["red"]])
        simulated = {
            "engine": "test_multi_batch",
            "status": "SIMULATED",
            "accessible_group_count": 2,
            "candidate_count": 4,
            "valid_candidate_count": 3,
            "search_truncated": False,
            "best": {
                "schedule_valid": True,
                "candidate_order": ["A", "B"],
                "candidate_batches": [{"groups": ["A", "B"]}],
                "simulated_pixels_removed": 1,
                "simulated_remaining_pixels": 0,
                "board_history": [["large internal payload"]],
            },
            "source_state_unchanged": True,
            "limitations": ["abstract timing"],
        }
        with patch.object(
            multi_batch_candidate_planner,
            "plan_multi_batch_candidates",
            return_value=simulated,
        ):
            result = run_multi_batch_diagnostic(state)

        self.assertEqual(result["status"], "SIMULATED")
        self.assertEqual(result["candidate_count"], 4)
        self.assertEqual(result["best"]["candidate_order"], ["A", "B"])
        self.assertNotIn("board_history", result)
        self.assertTrue(result["source_state_unchanged"])
        self.assertFalse(result["evidence_verified"])
        self.assertFalse(result["live_execution_allowed"])
        self.assertFalse(result["game_taps_enabled"])

    def test_multi_batch_diagnostic_fails_closed_on_planner_error(self):
        state = GameState([["red"]])
        with patch.object(
            multi_batch_candidate_planner,
            "plan_multi_batch_candidates",
            side_effect=RuntimeError("synthetic failure"),
        ):
            result = run_multi_batch_diagnostic(state)

        self.assertEqual(result["status"], "MULTI_BATCH_DIAGNOSTIC_ERROR")
        self.assertIn("synthetic failure", result["error"])
        self.assertFalse(result["live_execution_allowed"])
        self.assertFalse(result["game_taps_enabled"])

    def test_evolving_board_diagnostic_is_fail_closed_and_compact(self):
        from orchestration import run_evolving_board_diagnostic
        import evolving_board_planner
        state = GameState([["red"]])
        simulated = {
            "engine": "test_evolving",
            "status": "PARTIAL_SEQUENCE",
            "nodes_examined": 3,
            "search_truncated": False,
            "sequence": [{"group_id": "A", "shooter_ids": ["A"]}],
            "sequence_length": 1,
            "initial_pixels": 1,
            "simulated_pixels_removed": 1,
            "simulated_remaining_pixels": 0,
            "board_cleared": True,
            "known_group_count": 1,
            "unplanned_group_ids": [],
            "blockers": ["CONVEYOR_SCHEDULE_NOT_VALIDATED"],
            "source_state_unchanged": True,
            "limitations": ["abstract schedule"],
            "board_history": [["internal payload"]],
        }
        with patch.object(evolving_board_planner, "plan_evolving_board",
                          return_value=simulated) as planner:
            result = run_evolving_board_diagnostic(state)
        planner.assert_called_once()
        self.assertIsNone(planner.call_args.kwargs["accessibility_resolver"])
        self.assertEqual(result["status"], "PARTIAL_SEQUENCE")
        self.assertTrue(result["board_cleared"])
        self.assertFalse(result["full_level_complete"])
        self.assertFalse(result["evidence_verified"])
        self.assertFalse(result["live_execution_allowed"])
        self.assertFalse(result["game_taps_enabled"])
        self.assertNotIn("board_history", result)

    def test_evolving_board_diagnostic_fails_closed(self):
        from orchestration import run_evolving_board_diagnostic
        import evolving_board_planner
        with patch.object(evolving_board_planner, "plan_evolving_board",
                          side_effect=RuntimeError("synthetic failure")):
            result = run_evolving_board_diagnostic(GameState([["red"]]))
        self.assertEqual(result["status"], "EVOLVING_BOARD_DIAGNOSTIC_ERROR")
        self.assertFalse(result["full_level_complete"])
        self.assertFalse(result["game_taps_enabled"])

    def test_capacity_aware_diagnostic_is_fail_closed(self):
        from orchestration import run_capacity_aware_evolving_diagnostic
        import capacity_aware_evolving_planner
        state = GameState([["red"]])
        simulated = {
            "engine": "test_capacity",
            "status": "SIMULATED_SCHEDULE_COMPLETE",
            "board_plan": {"sequence": [{"group_id": "A"}]},
            "batches": [{"groups": ["A"]}],
            "schedule_valid": True,
            "initial_pixels": 1,
            "simulated_pixels_removed": 1,
            "simulated_remaining_pixels": 0,
            "board_cleared": True,
            "known_group_count": 1,
            "planned_group_count": 1,
            "unplanned_group_ids": [],
            "full_level_complete": True,
            "blockers": [],
            "source_state_unchanged": True,
            "limitations": [],
        }
        with patch.object(
            capacity_aware_evolving_planner,
            "plan_capacity_aware_evolving_schedule",
            return_value=simulated,
        ) as planner:
            result = run_capacity_aware_evolving_diagnostic(state)
        planner.assert_called_once()
        self.assertIsNone(planner.call_args.kwargs["accessibility_resolver"])
        self.assertTrue(result["schedule_valid"])
        self.assertFalse(result["full_level_complete"])
        self.assertFalse(result["evidence_verified"])
        self.assertFalse(result["game_taps_enabled"])

    def test_capacity_aware_diagnostic_fails_closed(self):
        from orchestration import run_capacity_aware_evolving_diagnostic
        import capacity_aware_evolving_planner
        with patch.object(
            capacity_aware_evolving_planner,
            "plan_capacity_aware_evolving_schedule",
            side_effect=RuntimeError("synthetic failure"),
        ):
            result = run_capacity_aware_evolving_diagnostic(GameState([["red"]]))
        self.assertEqual(result["status"], "CAPACITY_AWARE_DIAGNOSTIC_ERROR")
        self.assertFalse(result["full_level_complete"])
        self.assertFalse(result["game_taps_enabled"])


if __name__ == "__main__":
    unittest.main()
