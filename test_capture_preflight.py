import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from capture_preflight import validate_capture_pair


class CapturePreflightTests(unittest.TestCase):
    def write_pair(self, root, *, age_seconds=0, board_hash=None,
                   shooter_hash=None, board_session="session-abc",
                   shooter_session="session-abc", board_time=None,
                   shooter_time=None, verified=True):
        now = datetime.now(timezone.utc)
        timestamp = (now - timedelta(seconds=age_seconds)).isoformat()
        board_time = timestamp if board_time is None else board_time
        shooter_time = timestamp if shooter_time is None else shooter_time
        source_hash = board_hash or "a" * 64
        shooter_hash = source_hash if shooter_hash is None else shooter_hash
        board = {
            "source_sha256": source_hash,
            "snapshot_id": "sha256:" + source_hash,
            "board_snapshot_id": "sha256:" + source_hash,
            "capture_session_id": board_session,
            "captured_at": board_time,
            "same_board_state_confirmed": False,
            "gameplay_verified": False,
            "vision_classification_verified": False,
            "game_taps_enabled": False,
            "image_size": [1080, 2220],
            "grid_size": [35, 35],
        }
        shooter = {
            "observation_quality": {
                "colour_independently_verified": False,
                "ammunition_independently_verified": False,
                "slot_mapping_independently_verified": False,
            },
            "capture_provenance": {
                "verified": verified,
                "source_sha256": shooter_hash,
                "capture_session_id": shooter_session,
                "captured_at": shooter_time,
            }
        }
        board_path = Path(root) / "board.json"
        shooter_path = Path(root) / "shooters.json"
        board_path.write_text(json.dumps(board))
        shooter_path.write_text(json.dumps(shooter))
        audit_path = Path(root) / "source_pixel_audit_latest.json"
        audit_path.write_text(json.dumps({
            "schema_version": 1,
            "source_sha256": source_hash,
            "image_size": [1080, 2220],
            "grid_size": [35, 35],
            "capture_session_id": board_session,
            "captured_at": board_time,
            "snapshot_id": "sha256:" + source_hash,
            "board_snapshot_id": "sha256:" + source_hash,
            "sample_count": 1225,
            "reproduced_sample_count": 1225,
            "pixel_sample_mismatch_count": 0,
            "pixel_sample_mismatches": [],
            "label_mismatches": [],
            "pixel_samples_reproduced": True,
            "extraction_fingerprint_match": True,
            "label_mismatch_count": 0,
            "colour_counts_match": True,
            "source_image_hash_checked": True,
            "source_image_dimensions_checked": True,
            "label_truth_independently_verified": False,
            "calibration_alignment_verified": False,
            "gameplay_verified": False,
            "game_taps_enabled": False,
        }))
        return board_path, shooter_path, now

    def test_accepts_recent_matching_capture_pair(self):
        with tempfile.TemporaryDirectory() as directory:
            board, shooters, now = self.write_pair(directory)
            result = validate_capture_pair(board, shooters, now=now)
        self.assertTrue(result["valid"])
        self.assertTrue(result["freshness"]["fresh"])

    def test_rejects_missing_capture_files(self):
        with tempfile.TemporaryDirectory() as directory:
            result = validate_capture_pair(
                Path(directory) / "missing-board.json",
                Path(directory) / "missing-shooters.json",
            )
        self.assertFalse(result["valid"])
        self.assertIn("missing or invalid", result["reason"])

    def test_rejects_unverified_shooter_provenance(self):
        with tempfile.TemporaryDirectory() as directory:
            board, shooters, now = self.write_pair(directory, verified=False)
            result = validate_capture_pair(board, shooters, now=now)
        self.assertFalse(result["valid"])
        self.assertIn("not verified", result["reason"])

    def test_rejects_mismatched_screenshot_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            board, shooters, now = self.write_pair(
                directory, shooter_hash="b" * 64
            )
            result = validate_capture_pair(board, shooters, now=now)
        self.assertFalse(result["valid"])
        self.assertIn("screenshot hash", result["reason"])

    def test_rejects_mismatched_capture_session(self):
        with tempfile.TemporaryDirectory() as directory:
            board, shooters, now = self.write_pair(
                directory, shooter_session="different-session"
            )
            result = validate_capture_pair(board, shooters, now=now)
        self.assertFalse(result["valid"])
        self.assertIn("capture session", result["reason"])

    def test_rejects_stale_capture_pair(self):
        with tempfile.TemporaryDirectory() as directory:
            board, shooters, now = self.write_pair(
                directory, age_seconds=600
            )
            result = validate_capture_pair(board, shooters, now=now)
        self.assertFalse(result["valid"])
        self.assertIn("stale", result["reason"])

    def test_rejects_timestamp_without_timezone(self):
        with tempfile.TemporaryDirectory() as directory:
            board, shooters, now = self.write_pair(
                directory,
                board_time="2026-11-24T12:00:00",
                shooter_time="2026-11-24T12:00:00",
            )
            result = validate_capture_pair(board, shooters, now=now)
        self.assertFalse(result["valid"])
        self.assertIn("UTC offset", result["reason"])

    def test_rejects_inconsistent_board_snapshot_ids(self):
        with tempfile.TemporaryDirectory() as directory:
            board, shooters, now = self.write_pair(directory)
            data = json.loads(board.read_text())
            data["board_snapshot_id"] = "sha256:" + "b" * 64
            board.write_text(json.dumps(data))
            result = validate_capture_pair(board, shooters, now=now)
        self.assertFalse(result["valid"])
        self.assertIn("snapshot identifiers", result["reason"])


    def test_rejects_board_status_flags_that_are_true_or_missing(self):
        flag_names = (
            "same_board_state_confirmed",
            "gameplay_verified",
            "vision_classification_verified",
            "game_taps_enabled",
        )
        for flag in flag_names:
            for replacement in (True, None):
                with self.subTest(flag=flag, replacement=replacement), tempfile.TemporaryDirectory() as directory:
                    board, shooters, now = self.write_pair(directory)
                    data = json.loads(board.read_text())
                    if replacement is None:
                        del data[flag]
                    else:
                        data[flag] = replacement
                    board.write_text(json.dumps(data))
                    result = validate_capture_pair(board, shooters, now=now)
                    self.assertFalse(result["valid"])
                    self.assertIn(flag, result["reason"])

    def test_rejects_shooter_quality_flags_that_are_true_or_missing(self):
        flag_names = (
            "colour_independently_verified",
            "ammunition_independently_verified",
            "slot_mapping_independently_verified",
        )
        for flag in flag_names:
            for replacement in (True, None):
                with self.subTest(flag=flag, replacement=replacement), tempfile.TemporaryDirectory() as directory:
                    board, shooters, now = self.write_pair(directory)
                    data = json.loads(shooters.read_text())
                    if replacement is None:
                        del data["observation_quality"][flag]
                    else:
                        data["observation_quality"][flag] = replacement
                    shooters.write_text(json.dumps(data))
                    result = validate_capture_pair(board, shooters, now=now)
                    self.assertFalse(result["valid"])
                    self.assertIn(flag, result["reason"])

    def test_rejects_missing_shooter_observation_quality_object(self):
        with tempfile.TemporaryDirectory() as directory:
            board, shooters, now = self.write_pair(directory)
            data = json.loads(shooters.read_text())
            del data["observation_quality"]
            shooters.write_text(json.dumps(data))
            result = validate_capture_pair(board, shooters, now=now)
        self.assertFalse(result["valid"])
        self.assertIn("observation_quality", result["reason"])

    def test_rejects_required_source_pixel_audit_positive_flags_when_false_or_missing(self):
        for flag in ("source_image_hash_checked", "source_image_dimensions_checked"):
            for replacement in (False, None):
                with self.subTest(flag=flag, replacement=replacement), tempfile.TemporaryDirectory() as directory:
                    board, shooters, now = self.write_pair(directory)
                    audit_path = Path(directory) / "source_pixel_audit_latest.json"
                    data = json.loads(audit_path.read_text())
                    if replacement is None:
                        del data[flag]
                    else:
                        data[flag] = replacement
                    audit_path.write_text(json.dumps(data))
                    result = validate_capture_pair(board, shooters, now=now)
                    self.assertFalse(result["valid"])
                    self.assertIn(flag, result["reason"])

    def test_rejects_source_pixel_audit_unverified_flags_when_true_or_missing(self):
        flag_names = (
            "label_truth_independently_verified",
            "calibration_alignment_verified",
            "gameplay_verified",
            "game_taps_enabled",
        )
        for flag in flag_names:
            for replacement in (True, None):
                with self.subTest(flag=flag, replacement=replacement), tempfile.TemporaryDirectory() as directory:
                    board, shooters, now = self.write_pair(directory)
                    audit_path = Path(directory) / "source_pixel_audit_latest.json"
                    data = json.loads(audit_path.read_text())
                    if replacement is None:
                        del data[flag]
                    else:
                        data[flag] = replacement
                    audit_path.write_text(json.dumps(data))
                    result = validate_capture_pair(board, shooters, now=now)
                    self.assertFalse(result["valid"])
                    self.assertIn(flag, result["reason"])

    def test_rejects_inconsistent_pixel_audit_sample_coverage(self):
        mutations = (
            ("schema_version", 2),
            ("schema_version", True),
            ("sample_count", 1224),
            ("sample_count", True),
            ("reproduced_sample_count", 1224),
            ("reproduced_sample_count", True),
            ("pixel_sample_mismatch_count", 1),
            ("pixel_sample_mismatch_count", True),
            ("pixel_sample_mismatches", [{"row": 0, "column": 0}]),
            ("label_mismatches", [{"row": 0, "column": 0}]),
        )
        for field, value in mutations:
            with self.subTest(field=field, value=value), tempfile.TemporaryDirectory() as directory:
                board, shooters, now = self.write_pair(directory)
                audit_path = Path(directory) / "source_pixel_audit_latest.json"
                data = json.loads(audit_path.read_text())
                data[field] = value
                audit_path.write_text(json.dumps(data))
                result = validate_capture_pair(board, shooters, now=now)
                self.assertFalse(result["valid"])
                self.assertIn("pixel audit is incomplete", result["reason"])

    def test_rejects_missing_pixel_audit_coverage_fields(self):
        fields = (
            "schema_version",
            "sample_count",
            "reproduced_sample_count",
            "pixel_sample_mismatch_count",
            "pixel_sample_mismatches",
            "label_mismatches",
        )
        for field in fields:
            with self.subTest(field=field), tempfile.TemporaryDirectory() as directory:
                board, shooters, now = self.write_pair(directory)
                audit_path = Path(directory) / "source_pixel_audit_latest.json"
                data = json.loads(audit_path.read_text())
                del data[field]
                audit_path.write_text(json.dumps(data))
                result = validate_capture_pair(board, shooters, now=now)
                self.assertFalse(result["valid"])
                self.assertIn("pixel audit is incomplete", result["reason"])

    def test_rejects_missing_source_pixel_audit(self):
        with tempfile.TemporaryDirectory() as directory:
            board, shooters, now = self.write_pair(directory)
            (Path(directory) / "source_pixel_audit_latest.json").unlink()
            result = validate_capture_pair(board, shooters, now=now)
        self.assertFalse(result["valid"])
        self.assertIn("pixel audit is missing", result["reason"])

    def test_rejects_audit_for_different_screenshot(self):
        with tempfile.TemporaryDirectory() as directory:
            board, shooters, now = self.write_pair(directory)
            audit_path = Path(directory) / "source_pixel_audit_latest.json"
            audit = json.loads(audit_path.read_text())
            audit["source_sha256"] = "b" * 64
            audit_path.write_text(json.dumps(audit))
            result = validate_capture_pair(board, shooters, now=now)
        self.assertFalse(result["valid"])
        self.assertIn("not tied to this screenshot", result["reason"])

    def test_rejects_pixel_sample_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            board, shooters, now = self.write_pair(directory)
            audit_path = Path(directory) / "source_pixel_audit_latest.json"
            audit = json.loads(audit_path.read_text())
            audit["pixel_samples_reproduced"] = False
            audit_path.write_text(json.dumps(audit))
            result = validate_capture_pair(board, shooters, now=now)
        self.assertFalse(result["valid"])
        self.assertIn("pixel audit is incomplete", result["reason"])

    def test_rejects_audit_grid_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            board, shooters, now = self.write_pair(directory)
            audit_path = Path(directory) / "source_pixel_audit_latest.json"
            audit = json.loads(audit_path.read_text())
            audit["grid_size"] = [34, 35]
            audit_path.write_text(json.dumps(audit))
            result = validate_capture_pair(board, shooters, now=now)
        self.assertFalse(result["valid"])
        self.assertIn("pixel audit is incomplete", result["reason"])


    def test_rejects_audit_from_different_capture_session(self):
        with tempfile.TemporaryDirectory() as directory:
            board, shooters, now = self.write_pair(directory)
            audit_path = Path(directory) / "source_pixel_audit_latest.json"
            audit = json.loads(audit_path.read_text())
            audit["capture_session_id"] = "older-session"
            audit_path.write_text(json.dumps(audit))
            result = validate_capture_pair(board, shooters, now=now)
        self.assertFalse(result["valid"])
        self.assertIn("pixel audit is incomplete", result["reason"])

    def test_rejects_audit_from_different_capture_timestamp(self):
        with tempfile.TemporaryDirectory() as directory:
            board, shooters, now = self.write_pair(directory)
            audit_path = Path(directory) / "source_pixel_audit_latest.json"
            audit = json.loads(audit_path.read_text())
            audit["captured_at"] = (now - timedelta(seconds=30)).isoformat()
            audit_path.write_text(json.dumps(audit))
            result = validate_capture_pair(board, shooters, now=now)
        self.assertFalse(result["valid"])
        self.assertIn("pixel audit is incomplete", result["reason"])

    def test_rejects_audit_from_different_snapshot_identifier(self):
        with tempfile.TemporaryDirectory() as directory:
            board, shooters, now = self.write_pair(directory)
            audit_path = Path(directory) / "source_pixel_audit_latest.json"
            audit = json.loads(audit_path.read_text())
            audit["snapshot_id"] = "sha256:" + "b" * 64
            audit_path.write_text(json.dumps(audit))
            result = validate_capture_pair(board, shooters, now=now)
        self.assertFalse(result["valid"])
        self.assertIn("pixel audit is incomplete", result["reason"])


    def test_rejects_boolean_dimension_in_board_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            board, shooters, now = self.write_pair(directory)
            data = json.loads(board.read_text())
            data["image_size"] = [True, 2220]
            board.write_text(json.dumps(data))
            result = validate_capture_pair(board, shooters, now=now)
        self.assertFalse(result["valid"])
        self.assertIn("pixel audit is incomplete", result["reason"])

    def test_rejects_boolean_dimension_in_pixel_audit(self):
        with tempfile.TemporaryDirectory() as directory:
            board, shooters, now = self.write_pair(directory)
            audit_path = Path(directory) / "source_pixel_audit_latest.json"
            audit = json.loads(audit_path.read_text())
            audit["grid_size"] = [35, True]
            audit_path.write_text(json.dumps(audit))
            result = validate_capture_pair(board, shooters, now=now)
        self.assertFalse(result["valid"])
        self.assertIn("pixel audit is incomplete", result["reason"])

    def test_rejects_boolean_label_mismatch_count(self):
        with tempfile.TemporaryDirectory() as directory:
            board, shooters, now = self.write_pair(directory)
            audit_path = Path(directory) / "source_pixel_audit_latest.json"
            audit = json.loads(audit_path.read_text())
            audit["label_mismatch_count"] = False
            audit_path.write_text(json.dumps(audit))
            result = validate_capture_pair(board, shooters, now=now)
        self.assertFalse(result["valid"])
        self.assertIn("pixel audit is incomplete", result["reason"])

    def test_rejects_float_label_mismatch_count(self):
        with tempfile.TemporaryDirectory() as directory:
            board, shooters, now = self.write_pair(directory)
            audit_path = Path(directory) / "source_pixel_audit_latest.json"
            audit = json.loads(audit_path.read_text())
            audit["label_mismatch_count"] = 0.0
            audit_path.write_text(json.dumps(audit))
            result = validate_capture_pair(board, shooters, now=now)
        self.assertFalse(result["valid"])
        self.assertIn("pixel audit is incomplete", result["reason"])


    def test_rejects_duplicate_keys_in_capture_source_files(self):
        with tempfile.TemporaryDirectory() as directory:
            board = Path(directory) / "board.json"
            shooters = Path(directory) / "shooters.json"
            board.write_text('{"source_sha256":"first","source_sha256":"second"}')
            shooters.write_text('{"capture_provenance":{}}')
            result = validate_capture_pair(board, shooters)
        self.assertFalse(result["valid"])
        self.assertIn("Duplicate JSON object key", result["reason"])


if __name__ == "__main__":
    unittest.main()
