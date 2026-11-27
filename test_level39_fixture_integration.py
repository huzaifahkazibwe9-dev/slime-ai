"""Cross-module, offline-only integration tests for Level 39 fixtures.

These checks establish schema compatibility across existing auditors and
loaders. They do not authenticate source screenshots or establish live game
mechanics, colour truth, shooter identity, or a safe gameplay action.
"""

import json
import unittest
from pathlib import Path

from colour_mapping_auditor import audit as audit_colour_mapping
from planning_gate import evaluate_planning
from reachability_auditor import audit as audit_reachability
from shooter_loader import load_shooters
from vision_validator import audit_data as audit_vision

DATA = Path("data")


def _load(name):
    return json.loads((DATA / name).read_text())


def _run_fixture_chain():
    board = _load("vision_level39.json")
    shooter_data = _load("shooter_detection.json")
    mappings = _load("color_matches.json")
    calibration = _load("conveyor_calibration.json")
    observations = _load("conveyor_visual_observations.json")

    vision_report = audit_vision(board)
    colour_report = audit_colour_mapping(board, shooter_data, mappings)
    shooters = load_shooters()
    reachability_report = audit_reachability(
        board,
        calibration,
        observations,
    )
    planning_report = evaluate_planning(reachability_report)

    return {
        "vision": vision_report,
        "colour": colour_report,
        "shooters": shooters,
        "reachability": reachability_report,
        "planning": planning_report,
    }


class Level39FixtureIntegrationTests(unittest.TestCase):
    def test_board_shooter_colour_and_conveyor_fixtures_flow_together(self):
        reports = _run_fixture_chain()

        self.assertTrue(reports["vision"]["passed"])
        self.assertEqual(reports["vision"]["valid_rgb_samples"], 1225)
        self.assertEqual(
            [item["best_candidate"] for item in reports["colour"]["results"]],
            ["white", "cyan", "purple", "orange"],
        )
        self.assertEqual(
            set(reports["shooters"]),
            {"top_1", "top_2", "top_3", "top_4"},
        )
        self.assertEqual(len(reports["reachability"]["results"]), 8)
        self.assertEqual(
            {item["position_id"] for item in reports["reachability"]["results"]},
            {
                "bottom_1", "bottom_2", "right_1", "right_2",
                "top_1", "top_2", "left_1", "left_2",
            },
        )

    def test_integrated_evidence_stays_candidate_only_and_not_planning_ready(self):
        reports = _run_fixture_chain()
        colour = reports["colour"]
        reachability = reports["reachability"]
        planning = reports["planning"]

        self.assertFalse(colour["gameplay_verified"])
        self.assertFalse(colour["gameplay_taps_enabled"])
        self.assertTrue(all(not item["verified"] for item in colour["results"]))

        self.assertFalse(reachability["conveyor_identity_verified"])
        self.assertFalse(reachability["gameplay_verified"])
        self.assertFalse(reachability["game_taps_enabled"])
        self.assertEqual(reachability["planning_ready_positions"], 0)
        self.assertTrue(all(
            not item["planning_eligible"]
            for item in reachability["results"]
        ))

        self.assertEqual(planning["decision"], "NO_VERIFIED_PLANNING_CANDIDATES")
        self.assertEqual(planning["counts"]["eligible_scenarios"], 0)
        self.assertFalse(planning["planning_evidence_verified"])
        self.assertFalse(planning["gameplay_verified"])
        self.assertFalse(planning["game_taps_enabled"])
        self.assertFalse(planning["actions_performed"])

    def test_unknown_shooters_never_become_selectable_candidates(self):
        reports = _run_fixture_chain()
        shooters = reports["shooters"]

        self.assertTrue(all(not shooter.accessible for shooter in shooters.values()))
        self.assertTrue(all(
            shooter.screen_center is None
            and not shooter.screen_center_verified
            for shooter in shooters.values()
        ))
        self.assertEqual(
            {shooter.group_id for shooter in shooters.values()},
            {"bond_1", "bond_2"},
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
