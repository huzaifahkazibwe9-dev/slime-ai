import fcntl
import hashlib
import json
import os
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from capture_pipeline import (
    _capture_run_lock,
    _read_capture_snapshot,
    load_capture_config,
    run_capture_pipeline,
    validate_capture_outputs,
    audit_capture_pixels,
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
            "same_board_state_confirmed": False,
            "gameplay_verified": False,
            "vision_classification_verified": False,
            "game_taps_enabled": False,
        }))
        shooter_path.write_text(json.dumps({
            "observation_quality": {
                "colour_independently_verified": False,
                "ammunition_independently_verified": False,
                "slot_mapping_independently_verified": False,
            },
            "capture_provenance": {
                "verified": shooter_verified,
                "source_sha256": source_hash,
                "capture_session_id": session,
                "captured_at": captured_at,
                "capture_config_sha256": "c" * 64,
                "panel_bounds": [10, 20, 900, 600],
            },
            "bonding_source": "not_configured",
            "bonding_config_sha256": None,
        }))
        return board_path, shooter_path

    def test_capture_run_lock_excludes_a_second_open_file_description(self):
        with tempfile.TemporaryDirectory() as directory:
            lock_path = Path(directory) / "capture.lock"
            with _capture_run_lock(lock_path):
                with lock_path.open("a+") as competing_handle:
                    with self.assertRaises(BlockingIOError):
                        fcntl.flock(
                            competing_handle.fileno(),
                            fcntl.LOCK_EX | fcntl.LOCK_NB,
                        )

            # The lock is released even after its context exits, so another
            # process/invocation can acquire it and continue.
            with lock_path.open("a+") as next_handle:
                fcntl.flock(
                    next_handle.fileno(),
                    fcntl.LOCK_EX | fcntl.LOCK_NB,
                )
                fcntl.flock(next_handle.fileno(), fcntl.LOCK_UN)

    def test_capture_run_lock_is_released_when_capture_raises(self):
        with tempfile.TemporaryDirectory() as directory:
            lock_path = Path(directory) / "capture.lock"
            with self.assertRaisesRegex(RuntimeError, "simulated failure"):
                with _capture_run_lock(lock_path):
                    raise RuntimeError("simulated failure")

            with lock_path.open("a+") as next_handle:
                fcntl.flock(
                    next_handle.fileno(),
                    fcntl.LOCK_EX | fcntl.LOCK_NB,
                )
                fcntl.flock(next_handle.fileno(), fcntl.LOCK_UN)

    def test_rejects_unreadable_utf8_capture_config(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "capture.json"
            path.write_bytes(bytes((255, 254)))
            with self.assertRaisesRegex(ValueError, "valid UTF-8 JSON"):
                load_capture_config(path)

    def test_rejects_duplicate_capture_config_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "capture.json"
            path.write_text(
                '{"panel_bounds":[10,20,900,600],'
                '"capture_session_id":"first",'
                '"capture_session_id":"session-abc",'
                '"captured_at":"2026-11-23T12:30:00+03:00"}'
            )
            with self.assertRaisesRegex(ValueError, "valid UTF-8 JSON"):
                load_capture_config(path)

    def test_accepts_explicit_same_capture_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_config(directory, {
                "panel_bounds": [10, 20, 900, 600],
                "capture_session_id": "session-abc",
                "captured_at": "2026-11-23T12:30:00+03:00",
            })
            expected_config_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
            result = load_capture_config(path)
        self.assertEqual(result["panel_bounds"], [10, 20, 900, 600])
        self.assertEqual(result["capture_session_id"], "session-abc")
        self.assertEqual(result["captured_at"], "2026-11-23T12:30:00+03:00")
        self.assertEqual(result["config_sha256"], expected_config_sha256)

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

    def test_capture_snapshot_rejects_in_place_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.png"
            source.write_bytes(b"original screenshot bytes")
            real_fstat = os.fstat
            calls = []

            def mutate_before_final_stat(file_descriptor):
                calls.append(file_descriptor)
                if len(calls) == 2:
                    # Truncate the same inode while the descriptor is open.
                    source.write_bytes(b"changed")
                return real_fstat(file_descriptor)

            with patch(
                "capture_pipeline.os.fstat",
                side_effect=mutate_before_final_stat,
            ):
                with self.assertRaisesRegex(RuntimeError, "changed while"):
                    _read_capture_snapshot(source)

            self.assertEqual(len(calls), 2)

    def test_capture_snapshot_rejects_path_replacement_during_read(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.png"
            replacement = root / "replacement.png"
            source.write_bytes(b"original screenshot bytes")
            replacement.write_bytes(b"replacement screenshot bytes")
            real_fstat = os.fstat
            calls = []

            def replace_path_before_final_stat(file_descriptor):
                calls.append(file_descriptor)
                if len(calls) == 2:
                    replacement.replace(source)
                return real_fstat(file_descriptor)

            with patch(
                "capture_pipeline.os.fstat",
                side_effect=replace_path_before_final_stat,
            ):
                with self.assertRaisesRegex(RuntimeError, "changed while"):
                    _read_capture_snapshot(source)

            self.assertEqual(len(calls), 2)
            self.assertEqual(source.read_bytes(), b"replacement screenshot bytes")

    def test_runs_both_stages_from_one_private_immutable_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            screenshot = root / "source.jpg"
            screenshot.write_bytes(b"original screenshot bytes")
            config = self.write_config(directory, {
                "panel_bounds": [10, 20, 900, 600],
                "capture_session_id": "session-abc",
                "captured_at": "2026-11-23T12:30:00+03:00",
            })
            expected_config_sha256 = hashlib.sha256(config.read_bytes()).hexdigest()
            staged_paths = []

            def run_stage(command, check):
                if "screenshot_ingestor.py" in command:
                    staged = Path(command[2])
                else:
                    staged = Path(command[command.index("--source-screenshot") + 1])
                self.assertTrue(staged.is_file())
                self.assertEqual(staged.read_bytes(), b"original screenshot bytes")
                staged_paths.append(staged)
                if len(staged_paths) == 1:
                    # Simulate another process replacing the original after stage one.
                    screenshot.write_bytes(b"replacement screenshot bytes")

            with patch("capture_pipeline.subprocess.run", side_effect=run_stage) as run, patch(
                "capture_pipeline.validate_capture_outputs"
            ) as validate, patch("capture_pipeline.audit_capture_pixels") as audit:
                run_capture_pipeline(screenshot, config)

            self.assertEqual(run.call_count, 2)
            ingestor_args = run.call_args_list[0].args[0]
            detector_args = run.call_args_list[1].args[0]
            self.assertEqual(staged_paths[0], staged_paths[1])
            self.assertNotEqual(staged_paths[0], screenshot)
            self.assertFalse(staged_paths[0].exists())
            for flag in ("--capture-session-id", "session-abc",
                         "--captured-at", "2026-11-23T12:30:00+03:00"):
                self.assertIn(flag, ingestor_args)
                self.assertIn(flag, detector_args)
            self.assertIn("--extract-panel", detector_args)
            self.assertIn(expected_config_sha256, detector_args)
            self.assertIn("--capture-config-sha256", detector_args)
            self.assertEqual(
                detector_args[detector_args.index("--panel-bounds") + 1:
                              detector_args.index("--panel-bounds") + 5],
                ["10", "20", "900", "600"],
            )
            validate.assert_called_once()
            audit.assert_called_once()
            self.assertEqual(
                validate.call_args.args[2],
                hashlib.sha256(b"original screenshot bytes").hexdigest(),
            )
            self.assertEqual(audit.call_args.args[1], b"original screenshot bytes")

    def test_temporary_snapshot_is_removed_when_a_stage_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            screenshot = root / "source.jpg"
            screenshot.write_bytes(b"source bytes")
            config = self.write_config(directory, {
                "panel_bounds": [10, 20, 900, 600],
                "capture_session_id": "session-abc",
                "captured_at": "2026-11-23T12:30:00+03:00",
            })
            staged_paths = []

            def fail_stage(command, check):
                staged_paths.append(Path(command[2]))
                raise RuntimeError("simulated extraction failure")

            with patch("capture_pipeline.subprocess.run", side_effect=fail_stage):
                with self.assertRaisesRegex(RuntimeError, "extraction failure"):
                    run_capture_pipeline(screenshot, config)

            self.assertEqual(len(staged_paths), 1)
            self.assertFalse(staged_paths[0].exists())

    def test_rejects_board_observation_with_any_verified_or_missing_flag(self):
        flag_names = (
            "same_board_state_confirmed",
            "gameplay_verified",
            "vision_classification_verified",
            "game_taps_enabled",
        )
        for flag in flag_names:
            with self.subTest(flag=flag), tempfile.TemporaryDirectory() as directory:
                board, shooter = self.write_outputs(directory, "a" * 64)
                data = json.loads(board.read_text())
                data[flag] = True
                board.write_text(json.dumps(data))
                with self.assertRaisesRegex(ValueError, flag):
                    validate_capture_outputs(
                        board, shooter, "a" * 64, "session-abc",
                        "2026-11-23T12:30:00+03:00",
                    )

        with tempfile.TemporaryDirectory() as directory:
            board, shooter = self.write_outputs(directory, "a" * 64)
            data = json.loads(board.read_text())
            del data["gameplay_verified"]
            board.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, "gameplay_verified"):
                validate_capture_outputs(
                    board, shooter, "a" * 64, "session-abc",
                    "2026-11-23T12:30:00+03:00",
                )

    def test_rejects_shooter_observation_with_any_verified_or_missing_flag(self):
        flag_names = (
            "colour_independently_verified",
            "ammunition_independently_verified",
            "slot_mapping_independently_verified",
        )
        for flag in flag_names:
            with self.subTest(flag=flag), tempfile.TemporaryDirectory() as directory:
                board, shooter = self.write_outputs(directory, "a" * 64)
                data = json.loads(shooter.read_text())
                data["observation_quality"][flag] = True
                shooter.write_text(json.dumps(data))
                with self.assertRaisesRegex(ValueError, flag):
                    validate_capture_outputs(
                        board, shooter, "a" * 64, "session-abc",
                        "2026-11-23T12:30:00+03:00",
                    )

        with tempfile.TemporaryDirectory() as directory:
            board, shooter = self.write_outputs(directory, "a" * 64)
            data = json.loads(shooter.read_text())
            del data["observation_quality"]["ammunition_independently_verified"]
            shooter.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, "ammunition_independently_verified"):
                validate_capture_outputs(
                    board, shooter, "a" * 64, "session-abc",
                    "2026-11-23T12:30:00+03:00",
                )

    def test_rejects_missing_shooter_observation_quality_object(self):
        with tempfile.TemporaryDirectory() as directory:
            board, shooter = self.write_outputs(directory, "a" * 64)
            data = json.loads(shooter.read_text())
            del data["observation_quality"]
            shooter.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, "observation_quality"):
                validate_capture_outputs(
                    board, shooter, "a" * 64, "session-abc",
                    "2026-11-23T12:30:00+03:00",
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

    def test_rejects_user_confirmed_bond_source_without_config_digest(self):
        with tempfile.TemporaryDirectory() as directory:
            board, shooter = self.write_outputs(directory, "a" * 64)
            data = json.loads(shooter.read_text())
            data["bonding_source"] = "user_confirmed"
            data["bonding_config_sha256"] = None
            shooter.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, "exact SHA-256"):
                validate_capture_outputs(
                    board, shooter, "a" * 64, "session-abc",
                    "2026-11-23T12:30:00+03:00",
                )

    def test_rejects_malformed_bond_config_digest(self):
        with tempfile.TemporaryDirectory() as directory:
            board, shooter = self.write_outputs(directory, "a" * 64)
            data = json.loads(shooter.read_text())
            data["bonding_source"] = "not_user_confirmed"
            data["bonding_config_sha256"] = "not-a-digest"
            shooter.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, "exact SHA-256"):
                validate_capture_outputs(
                    board, shooter, "a" * 64, "session-abc",
                    "2026-11-23T12:30:00+03:00",
                )

    def test_rejects_capture_config_hash_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            board, shooter = self.write_outputs(directory, "a" * 64)
            with self.assertRaisesRegex(ValueError, "config hash"):
                validate_capture_outputs(
                    board, shooter, "a" * 64, "session-abc",
                    "2026-11-23T12:30:00+03:00",
                    expected_config_sha256="d" * 64,
                    expected_panel_bounds=[10, 20, 900, 600],
                )

    def test_rejects_panel_bounds_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            board, shooter = self.write_outputs(directory, "a" * 64)
            with self.assertRaisesRegex(ValueError, "panel bounds"):
                validate_capture_outputs(
                    board, shooter, "a" * 64, "session-abc",
                    "2026-11-23T12:30:00+03:00",
                    expected_config_sha256="c" * 64,
                    expected_panel_bounds=[11, 20, 900, 600],
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


    def test_audit_capture_pixels_persists_report_only_when_all_checks_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            board_path = Path(directory) / "board.json"
            output_path = Path(directory) / "audit.json"
            board_path.write_text(json.dumps({
                "fixture": True,
                "capture_session_id": "session-abc",
                "captured_at": "2026-11-25T12:00:00+00:00",
                "snapshot_id": "sha256:" + "a" * 64,
                "board_snapshot_id": "sha256:" + "a" * 64,
            }))
            report = {
                "pixel_samples_reproduced": True,
                "extraction_fingerprint_match": True,
                "label_mismatch_count": 0,
                "colour_counts_match": True,
            }
            with patch("capture_pipeline.audit_source_pixels", return_value=report):
                result = audit_capture_pixels(board_path, b"source", output_path)
            self.assertEqual(result["pixel_samples_reproduced"], True)
            self.assertEqual(result["capture_session_id"], "session-abc")
            self.assertEqual(result["captured_at"], "2026-11-25T12:00:00+00:00")
            self.assertEqual(result["snapshot_id"], "sha256:" + "a" * 64)
            self.assertRegex(
                result["board_observation_sha256"], r"^[0-9a-f]{64}$"
            )
            self.assertEqual(
                result["board_observation_sha256"],
                hashlib.sha256(
                    json.dumps(
                        json.loads(board_path.read_text()),
                        sort_keys=True, separators=(",", ":"), allow_nan=False,
                    ).encode("utf-8")
                ).hexdigest(),
            )
            self.assertEqual(json.loads(output_path.read_text()), result)

    def test_audit_capture_pixels_rejects_unreadable_utf8_observation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            board_path = root / "board.json"
            board_path.write_bytes(bytes((255, 254)))
            with self.assertRaisesRegex(
                ValueError, "missing or invalid for pixel audit"
            ):
                audit_capture_pixels(board_path, b"source screenshot bytes")

    def test_audit_capture_pixels_rejects_duplicate_json_keys(self):
        with tempfile.TemporaryDirectory() as directory:
            board_path = Path(directory) / "board.json"
            board_path.write_text(
                '{"source_sha256":"first","source_sha256":"second"}'
            )
            with self.assertRaisesRegex(
                ValueError, "missing or invalid for pixel audit"
            ):
                audit_capture_pixels(board_path, b"source screenshot bytes")

    def test_audit_capture_pixels_rejects_sample_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            board_path = Path(directory) / "board.json"
            board_path.write_text(json.dumps({"fixture": True}))
            report = {
                "pixel_samples_reproduced": False,
                "extraction_fingerprint_match": True,
                "label_mismatch_count": 0,
                "colour_counts_match": True,
            }
            with patch("capture_pipeline.audit_source_pixels", return_value=report):
                with self.assertRaisesRegex(ValueError, "RGB sample mismatches"):
                    audit_capture_pixels(board_path, b"source", Path(directory) / "audit.json")

    def test_audit_capture_pixels_rejects_missing_fingerprint(self):
        with tempfile.TemporaryDirectory() as directory:
            board_path = Path(directory) / "board.json"
            board_path.write_text(json.dumps({"fixture": True}))
            report = {
                "pixel_samples_reproduced": True,
                "extraction_fingerprint_match": False,
                "label_mismatch_count": 0,
                "colour_counts_match": True,
            }
            with patch("capture_pipeline.audit_source_pixels", return_value=report):
                with self.assertRaisesRegex(ValueError, "fingerprint"):
                    audit_capture_pixels(board_path, b"source", Path(directory) / "audit.json")



    def test_audit_capture_pixels_rejects_boolean_mismatch_count(self):
        with tempfile.TemporaryDirectory() as directory:
            board_path = Path(directory) / "board.json"
            board_path.write_text(json.dumps({"fixture": True}))
            report = {
                "pixel_samples_reproduced": True,
                "extraction_fingerprint_match": True,
                "label_mismatch_count": False,
                "colour_counts_match": True,
            }
            with patch("capture_pipeline.audit_source_pixels", return_value=report):
                with self.assertRaisesRegex(ValueError, "labels do not match"):
                    audit_capture_pixels(
                        board_path, b"source", Path(directory) / "audit.json"
                    )
            self.assertFalse((Path(directory) / "audit.json").exists())


if __name__ == "__main__":
    unittest.main()
