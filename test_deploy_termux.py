import os
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path


SOURCE_SCRIPT = Path(__file__).with_name("deploy_termux.sh")


class TermuxDeploymentTests(unittest.TestCase):
    def make_environment(self, root, with_capture_config=False):
        root = Path(root)
        (root / ".git").mkdir()
        (root / "screenshots").mkdir()
        (root / "data").mkdir()
        (root / "screenshots" / "level39.jpg").write_bytes(b"synthetic screenshot")
        (root / "data" / "shooter_detection.json").write_text("{}")
        if with_capture_config:
            (root / "data" / "shooter_capture_config.json").write_text("{}")
        (root / "requirements.txt").write_text(
            "Pillow>=10.0\nnumpy>=1.26\n"
        )
        shutil.copy2(SOURCE_SCRIPT, root / "deploy_termux.sh")

        build_marker = root / "build-ran.txt"
        (root / "build_pipeline.sh").write_text(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            'printf "built" > "$BUILD_MARKER"\n'
        )

        bin_dir = root / "bin"
        bin_dir.mkdir()
        log_path = root / "commands.log"

        stubs = {
            "git": 'printf "git %s\\n" "$*" >> "$FAKE_LOG"\n',
            "pkg": 'printf "pkg %s\\n" "$*" >> "$FAKE_LOG"\n',
            "python": (
                'printf "python %s\\n" "$*" >> "$FAKE_LOG"\n'
                'if [[ "${1:-}" == "--version" ]]; then echo "Python 3.12.0"; fi\n'
                "exit 0\n"
            ),
        }
        if with_capture_config:
            stubs["tesseract"] = (
                'if [[ "${1:-}" == "--list-langs" ]]; then\n'
                '  printf "List of available languages (1):\\neng\\n"\n'
                "fi\n"
                "exit 0\n"
            )

        for name, body in stubs.items():
            stub_path = bin_dir / name
            stub_path.write_text("#!/usr/bin/env bash\nset -euo pipefail\n" + body)
            stub_path.chmod(stub_path.stat().st_mode | stat.S_IXUSR)

        env = os.environ.copy()
        env.update({
            "PATH": str(bin_dir) + os.pathsep + env.get("PATH", ""),
            "PREFIX": "/data/data/com.termux/files/usr",
            "FAKE_LOG": str(log_path),
            "BUILD_MARKER": str(build_marker),
        })
        return env, log_path, build_marker

    def run_deployment(self, root, env):
        return subprocess.run(
            ["bash", str(Path(root) / "deploy_termux.sh")],
            cwd=root,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_installs_native_packages_without_pip_and_runs_build(self):
        with tempfile.TemporaryDirectory() as directory:
            env, log_path, build_marker = self.make_environment(directory)
            result = self.run_deployment(directory, env)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(build_marker.is_file())
            commands = log_path.read_text()
            self.assertIn("pkg install -y python python-numpy python-pillow", commands)
            self.assertNotIn("pkg install -y tesseract", commands)
            self.assertNotIn("python -m pip", commands)

    def test_installs_tesseract_when_capture_configuration_requires_ocr(self):
        with tempfile.TemporaryDirectory() as directory:
            env, log_path, build_marker = self.make_environment(
                directory, with_capture_config=True
            )
            result = self.run_deployment(directory, env)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(build_marker.is_file())
            commands = log_path.read_text()
            self.assertIn("pkg install -y python python-numpy python-pillow", commands)
            self.assertIn("pkg install -y tesseract", commands)

    def test_refuses_non_termux_environment_before_running_commands(self):
        with tempfile.TemporaryDirectory() as directory:
            env, log_path, build_marker = self.make_environment(directory)
            env["PREFIX"] = "/usr/local"
            result = self.run_deployment(directory, env)

            self.assertEqual(result.returncode, 2)
            self.assertIn("intended for Termux", result.stderr)
            self.assertFalse(log_path.exists())
            self.assertFalse(build_marker.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
