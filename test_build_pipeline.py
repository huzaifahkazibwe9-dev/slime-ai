import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent
PIPELINE = ROOT / "build_pipeline.sh"


class BuildPipelineContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.script = PIPELINE.read_text(encoding="utf-8")

    def test_pipeline_uses_fail_fast_shell_mode(self):
        self.assertIn("set -euo pipefail", self.script)

    def test_thirteen_stage_numbers_are_present(self):
        stage_numbers = [
            int(value)
            for value in re.findall(r"\[(\d+)/13\]", self.script)
        ]
        self.assertEqual(set(stage_numbers), set(range(1, 14)))
        for stage in range(3, 14):
            self.assertEqual(stage_numbers.count(stage), 1)
        # Stages 1 and 2 have alternate branches for capture modes.
        self.assertEqual(stage_numbers.count(1), 3)
        self.assertEqual(stage_numbers.count(2), 2)

    def test_blank_bond_config_is_prepared_before_shooter_detection(self):
        prepare = self.script.index("python prepare_bonded_groups_config.py")
        capture = min(
            position for position in (
                self.script.find("python capture_pipeline.py"),
                self.script.find("python shooter_detector.py"),
            )
            if position >= 0
        )
        self.assertLess(prepare, capture)

    def test_identity_and_snapshot_stages_precede_reachability(self):
        ordered_commands = (
            'python snapshot_sync.py --board "$OBSERVATION"',
            'python prepare_identity_observations.py --board "$OBSERVATION"',
            'python identity_auditor.py --board "$OBSERVATION"',
            "python conveyor_identity_matcher.py",
            'python reachability_auditor.py --board "$OBSERVATION"',
            'python reachability_confidence.py --board "$OBSERVATION"',
            "python planning_gate.py",
            'python orchestration.py --observation "$OBSERVATION"',
        )
        positions = [self.script.index(command) for command in ordered_commands]
        self.assertEqual(positions, sorted(positions))

    def test_every_planning_stage_uses_the_same_board_observation_path(self):
        self.assertIn('OBSERVATION="data/board_observation_latest.json"', self.script)
        self.assertIn('python snapshot_sync.py --board "$OBSERVATION"', self.script)
        self.assertIn('python reachability_auditor.py --board "$OBSERVATION"', self.script)
        self.assertIn('python reachability_confidence.py --board "$OBSERVATION"', self.script)
        self.assertIn('python orchestration.py --observation "$OBSERVATION"', self.script)
        self.assertIn('python main.py --observation "$OBSERVATION"', self.script)
        self.assertIn(
            'python readiness_coordinator.py --observation "$OBSERVATION"',
            self.script,
        )

    def test_pipeline_keeps_live_game_actions_disabled(self):
        self.assertIn("Live game actions: DISABLED", self.script)
        self.assertIn("No game taps were performed.", self.script)
        self.assertIn("Live game actions remain disabled.", self.script)
        self.assertNotRegex(self.script, r"adb\s+shell\s+input\s+(tap|swipe|text)")
        self.assertNotRegex(self.script, r"input\s+(tap|swipe)\b")

    def test_full_unit_suite_is_the_final_stage(self):
        last = self.script.index("python -m unittest discover -q")
        self.assertGreater(last, self.script.index("readiness_coordinator.py"))
        self.assertEqual(
            self.script.count("python -m unittest discover -q"),
            1,
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
