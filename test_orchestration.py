import unittest
from orchestration import evidence_status


class OrchestrationTests(unittest.TestCase):
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
        }
        identity = {
            "identity_verified": True,
            "timestamps_known": True,
            "errors": [],
            "blockers": [],
        }
        snapshot = {
            "synchronised": True,
            "planning_allowed_by_sync": True,
        }
        candidates = {"identity_verified": True}
        result = evidence_status(planning, identity, snapshot, candidates)
        self.assertTrue(result["evidence_gate_passed"])

    def test_live_actions_always_disabled(self):
        result = evidence_status({}, {}, {}, {})
        self.assertIs(result["game_taps_enabled"], False)
        self.assertIs(result["actions_performed"], False)


if __name__ == "__main__":
    unittest.main()
