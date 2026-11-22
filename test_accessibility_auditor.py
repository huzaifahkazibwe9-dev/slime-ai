import unittest
from game_state import GameState, Shooter
from accessibility_auditor import audit_accessibility


def make_state():
    shooters = {
        "A": Shooter(
            id="A", color="red", ammo=2, accessible=True,
            group_id="pair", bonded_ids=["B"],
            panel_center=(100, 100),
        ),
        "B": Shooter(
            id="B", color="blue", ammo=2, accessible=True,
            group_id="pair", bonded_ids=["A"],
            panel_center=(200, 100),
        ),
    }
    return GameState(
        board=[[None]], shooters=shooters
    )


class AccessibilityAuditorTests(unittest.TestCase):
    def test_unverified_tappability_blocks_group(self):
        state = make_state()
        report = audit_accessibility(state)
        self.assertEqual(report["groups_checked"], 1)
        self.assertEqual(report["eligible_groups"], 0)
        self.assertIn(
            "NO_VERIFIED_TAPPABILITY_OBSERVATION",
            report["results"][0]["reasons"],
        )

    def test_verified_observation_allows_audit_eligibility(self):
        state = make_state()
        report = audit_accessibility(
            state, {"A|B": {"tappable": True}}
        )
        self.assertEqual(report["eligible_groups"], 1)

    def test_insufficient_capacity_blocks_group(self):
        state = make_state()
        state.conveyor = ["X", "Y", "Z", "W"]
        report = audit_accessibility(
            state, {"A|B": {"tappable": True}}
        )
        self.assertIn(
            "INSUFFICIENT_CONVEYOR_CAPACITY",
            report["results"][0]["reasons"],
        )

    def test_existing_storage_blocks_group(self):
        state = make_state()
        state.storage = ["A"]
        report = audit_accessibility(
            state, {"A|B": {"tappable": True}}
        )
        self.assertIn(
            "GROUP_ALREADY_IN_CONVEYOR_OR_STORAGE",
            report["results"][0]["reasons"],
        )

    def test_source_state_is_unchanged(self):
        state = make_state()
        before = (
            state.conveyor[:],
            state.storage[:],
            {
                key: value.accessible
                for key, value in state.shooters.items()
            },
        )
        audit_accessibility(
            state, {"A|B": {"tappable": True}}
        )
        after = (
            state.conveyor[:],
            state.storage[:],
            {
                key: value.accessible
                for key, value in state.shooters.items()
            },
        )
        self.assertEqual(before, after)

    def test_gameplay_actions_remain_disabled(self):
        report = audit_accessibility(
            make_state(), {"A|B": {"tappable": True}}
        )
        self.assertFalse(report["game_taps_enabled"])
        self.assertFalse(report["live_execution_allowed"])


if __name__ == "__main__":
    unittest.main()
