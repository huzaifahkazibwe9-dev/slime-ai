import hashlib
import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from capture_pipeline import (
    load_capture_config,
    run_capture_pipeline,
    validate_capture_outputs,
)


class CapturePipelineConfigTests(unittest.TestCase):
    def write_config(self, root, value):
        path = Path(root) / "capture.json"
        path.write_text(json.dumps(value))
        return path

    def write_outputs(self, root, source_hash, session="session-abc",
                      captured_at="2026-11-23T12:30:00+03:00",
                      shooter_verified=True):
        board_path = Path(root) / "board.json"
        shooter_path = Path(root) / "shooter.json"
        board_path.write_text(json.dumps({
            "source_sha256": source_hash,
            "snapshot_id": "sha256:" + source_hash,
            "board_snapshot_id": "sha256:" + source_hash,
            "capture_session_id": session,
            "captured_at": captured_at,
        }))
        shooter_path.write_text(json.dumps({
            "capture_provenance": {
                "verified": shooter_verified,
                "source_sha256": source_hash,
                "capture_session_id": session,
                "captured_at": captured_at,
            }
        }))
        return board_path, shooter_path

    def test_accepts_explicit_same_capture_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_config(directory, {
                "panel_bounds": [10, 20, 900, 600],
                "capture_session_id": "session-abc",
                "captured_at": "2026-11-23T12:30:00+03:00",
            })
            result = load_capture_config(path)
        self.assertEqual(result["panel_bounds"], [10, 20, 900, 600])
        self.assertEqual(result["capture_session_id"], "session-abc")
        self.assertEqual(result["captured_at"], "2026-11-23T12:30:00+03:00")

    def test_rejects_missing_session_id(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_config(directory, {
                "panel_bounds": [10, 20, 900, 600],
                "captured_at": "2026-11-23T12:30:00+03:00",
            })
            with self.assertRaisesRegex(ValueError, "session_id"):
                load_capture_config(path)

    def test_rejects_timestamp_without_utc_offset(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_config(directory, {
                "panel_bounds": [10, 20, 900, 600],
                "capture_session_id": "session-abc",
                "captured_at": "2026-11-23T12:30:00",
            })
            with self.assertRaisesRegex(ValueError, "UTC offset"):
                load_capture_config(path)

    def test_runs_ingestor_and_detector_with_identical_capture_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            screenshot = root / "source.jpg"
            screenshot.write_bytes(b"placeholder")
            config = self.write_config(directory, {
                "panel_bounds": [10, 20, 900, 600],
                "capture_session_id": "session-abc",
                "captured_at": "2026-11-23T12:30:00+03:00",
            })
            with patch("capture_pipeline.subprocess.run") as run, patch(
                "capture_pipeline.validate_capture_outputs"
            ) as validate:
                run_capture_pipeline(screenshot, config)
        self.assertEqual(run.call_count, 2)
        ingestor_args = run.call_args_list[0].args[0]
        detector_args = run.call_args_list[1].args[0]
        for flag in ("--capture-session-id", "session-abc",
                     "--captured-at", "2026-11-23T12:30:00+03:00"):
            self.assertIn(flag, ingestor_args)
            self.assertIn(flag, detector_args)
        self.assertIn("--extract-panel", detector_args)
        self.assertEqual(
            detector_args[detector_args.index("--panel-bounds") + 1:
                          detector_args.index("--panel-bounds") + 5],
            ["10", "20", "900", "600"],
        )
        validate.assert_called_once()
        self.assertEqual(
            validate.call_args.args[2],
            hashlib.sha256(b"placeholder").hexdigest(),
        )

    def test_rejects_board_hash_that_differs_from_input_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            board, shooter = self.write_outputs(directory, "a" * 64)
            with self.assertRaisesRegex(ValueError, "Board observation"):
                validate_capture_outputs(
                    board, shooter, "b" * 64, "session-abc",
                    "2026-11-23T12:30:00+03:00",
                )

    def test_rejects_shooter_hash_that_differs_from_board_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            board, shooter = self.write_outputs(directory, "a" * 64)
            data = json.loads(shooter.read_text())
            data["capture_provenance"]["source_sha256"] = "b" * 64
            shooter.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, "Shooter observation"):
                validate_capture_outputs(
                    board, shooter, "a" * 64, "session-abc",
                    "2026-11-23T12:30:00+03:00",
                )

    def test_rejects_capture_session_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            board, shooter = self.write_outputs(
                directory, "a" * 64, session="different-session"
            )
            with self.assertRaisesRegex(ValueError, "Board capture session"):
                validate_capture_outputs(
                    board, shooter, "a" * 64, "session-abc",
                    "2026-11-23T12:30:00+03:00",
                )

    def test_rejects_unverified_shooter_provenance(self):
        with tempfile.TemporaryDirectory() as directory:
            board, shooter = self.write_outputs(
                directory, "a" * 64, shooter_verified=False
            )
            with self.assertRaisesRegex(ValueError, "not verified"):
                validate_capture_outputs(
                    board, shooter, "a" * 64, "session-abc",
                    "2026-11-23T12:30:00+03:00",
                )

    def test_rejects_non_integer_crop_bounds(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_config(directory, {
                "panel_bounds": [10, 20, "900", 600],
                "capture_session_id": "session-abc",
                "captured_at": "2026-11-23T12:30:00+03:00",
            })
            with self.assertRaisesRegex(ValueError, "integer coordinates"):
                load_capture_config(path)


if __name__ == "__main__":
    unittest.main()
