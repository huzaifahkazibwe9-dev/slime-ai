"""Isolated shell-flow tests for the offline build pipeline.

A stub Python executable records invoked modules. No production Python module,
Android device, or live-game interaction is executed by these tests.
"""

import os
import tempfile
import unittest
from pathlib import Path
import subprocess


class BuildPipelineShellTests(unittest.TestCase):
    def run_pipeline(self, *, screenshot=True, capture_config=False, shooter_data=False):
        root = Path(tempfile.mkdtemp())
        (root / "screenshots").mkdir()
        (root / "data").mkdir()
        script = root / "build_pipeline.sh"
        script.write_text(
            Path(__file__).with_name("build_pipeline.sh").read_text()
        )

        if screenshot:
            (root / "screenshots" / "level39.jpg").write_bytes(b"fixture-only")
        if capture_config:
            (root / "data" / "shooter_capture_config.json").write_text("{}")
        if shooter_data:
            (root / "data" / "shooter_detection.json").write_text("{}")

        fake_bin = root / "fake-bin"
        fake_bin.mkdir()
        trace = root / "python-commands.log"
        python_stub = fake_bin / "python"
        python_stub.write_text(
            "#!/bin/sh\n"
            'printf "%s\\n" "$*" >> "$SLIME_TEST_TRACE"\n'
            "exit 0\n"
        )
        python_stub.chmod(0o755)

        env = os.environ.copy()
        env["PATH"] = str(fake_bin) + os.pathsep + env.get("PATH", "")
        env["SLIME_TEST_TRACE"] = str(trace)

        result = subprocess.run(
            ["bash", str(script)],
            cwd=root,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        commands = trace.read_text().splitlines() if trace.exists() else []
        return root, result, commands

    def test_missing_screenshot_fails_before_python_commands(self):
        root, result, commands = self.run_pipeline(screenshot=False)
        self.addCleanup(lambda: __import__("shutil").rmtree(root, ignore_errors=True))
        self.assertEqual(result.returncode, 2)
        self.assertIn("Required screenshot not found", result.stderr)
        self.assertEqual(commands, [])

    def test_missing_shooter_sources_fail_before_board_ingestion(self):
        root, result, commands = self.run_pipeline(
            screenshot=True,
            capture_config=False,
            shooter_data=False,
        )
        self.addCleanup(lambda: __import__("shutil").rmtree(root, ignore_errors=True))
        self.assertEqual(result.returncode, 2)
        self.assertIn("Need data/shooter_capture_config.json", result.stderr)
        self.assertTrue(any(command.startswith("calibrate_shooter_panel.py ") for command in commands))
        self.assertFalse(any(command.startswith("screenshot_ingestor.py ") for command in commands))
        self.assertFalse(any(command.startswith("capture_pipeline.py ") for command in commands))

    def test_existing_shooter_detection_is_preserved_for_provenance_recheck(self):
        root, result, commands = self.run_pipeline(
            screenshot=True,
            capture_config=False,
            shooter_data=True,
        )
        self.addCleanup(lambda: __import__("shutil").rmtree(root, ignore_errors=True))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Preserving existing shooter detection", result.stdout)
        self.assertTrue(any(command.startswith("screenshot_ingestor.py ") for command in commands))
        self.assertFalse(any(command.startswith("shooter_detector.py") for command in commands))
        self.assertFalse(any(command.startswith("capture_pipeline.py ") for command in commands))
        self.assertTrue(any(command == "-m unittest discover -q" for command in commands))
        self.assertIn("No game taps were performed", result.stdout)

    def test_same_capture_config_selects_capture_pipeline(self):
        root, result, commands = self.run_pipeline(
            screenshot=True,
            capture_config=True,
            shooter_data=False,
        )
        self.addCleanup(lambda: __import__("shutil").rmtree(root, ignore_errors=True))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(any(command.startswith("capture_pipeline.py ") for command in commands))
        self.assertFalse(any(command.startswith("screenshot_ingestor.py ") for command in commands))
        self.assertFalse(any(command.startswith("shooter_detector.py") for command in commands))
        self.assertIn("Live game actions remain disabled", result.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
