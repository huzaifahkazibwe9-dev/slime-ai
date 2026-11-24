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
            "image_size": [1080, 2220],
            "grid_size": [35, 35],
        }
        shooter = {
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
            "source_sha256": source_hash,
            "image_size": [1080, 2220],
            "grid_size": [35, 35],
            "capture_session_id": board_session,
            "captured_at": board_time,
            "snapshot_id": "sha256:" + source_hash,
            "board_snapshot_id": "sha256:" + source_hash,
            "pixel_samples_reproduced": True,
            "extraction_fingerprint_match": True,
            "label_mismatch_count": 0,
            "colour_counts_match": True,
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


if __name__ == "__main__":
    unittest.main()
