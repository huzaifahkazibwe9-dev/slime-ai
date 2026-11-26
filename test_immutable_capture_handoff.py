import json
import tempfile
import unittest
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from capture_preflight import validate_capture_pair
from orchestration import _read_capture_bundle
from screenshot_observation_loader import load_observed_level
from level_loader import load_level
from source_pixel_audit import canonical_observation_sha256


class ImmutableCaptureHandoffTests(unittest.TestCase):
    def _write_bundle(self, root):
        digest = "a" * 64
        captured_at = datetime.now(timezone.utc).isoformat()
        board = {
            "source_sha256": digest,
            "snapshot_id": "sha256:" + digest,
            "board_snapshot_id": "sha256:" + digest,
            "capture_session_id": "session-abc",
            "captured_at": captured_at,
            "timestamp_identified": True,
            "same_board_state_confirmed": False,
            "image_size": [1080, 2220],
            "grid_size": [35, 35],
            "gameplay_verified": False,
            "vision_classification_verified": False,
            "game_taps_enabled": False,
            "board": [["dark"]],
            "raw_rgb": [[[0, 0, 0]]],
            "counts": {"dark": 1},
        }
        shooters = {
            "observation_quality": {
                "colour_independently_verified": False,
                "ammunition_independently_verified": False,
                "slot_mapping_independently_verified": False,
            },
            "visible_shooters": [],
            "bonded_groups": [],
            "capture_provenance": {
                "verified": True,
                "source_sha256": digest,
                "capture_session_id": "session-abc",
                "captured_at": captured_at,
            },
        }
        audit = {
            "schema_version": 1,
            "source_sha256": digest,
            "board_observation_sha256": canonical_observation_sha256(board),
            "image_size": [1080, 2220],
            "grid_size": [35, 35],
            "capture_session_id": "session-abc",
            "captured_at": captured_at,
            "snapshot_id": "sha256:" + digest,
            "board_snapshot_id": "sha256:" + digest,
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
        }
        board_path = Path(root) / "board.json"
        shooter_path = Path(root) / "shooters.json"
        audit_path = Path(root) / "source_pixel_audit_latest.json"
        board_path.write_text(json.dumps(board))
        shooter_path.write_text(json.dumps(shooters))
        audit_path.write_text(json.dumps(audit))
        return board_path, shooter_path, audit_path, board, shooters, audit

    def test_preflight_and_loader_use_pinned_objects_after_files_change(self):
        with tempfile.TemporaryDirectory() as directory:
            board_path, shooter_path, audit_path, board, shooters, audit = (
                self._write_bundle(directory)
            )
            pinned = _read_capture_bundle(board_path, shooter_path, audit_path)

            # Simulate concurrent replacement immediately after the one-time
            # read. Downstream preflight/loading must not consult these paths.
            board_path.write_text(json.dumps({"source_sha256": "b" * 64}))
            shooter_path.write_text(json.dumps({"visible_shooters": []}))
            audit_path.write_text(json.dumps({"invalidated": True}))

            result = validate_capture_pair(
                board_path,
                shooter_path,
                board_data=pinned["board_data"],
                shooter_data=pinned["shooter_data"],
                pixel_audit_data=pinned["pixel_audit_data"],
            )
            self.assertTrue(result["valid"], result.get("reason"))
            self.assertIs(result["board_data"], pinned["board_data"])
            self.assertIs(result["shooter_data"], pinned["shooter_data"])
            self.assertIs(result["pixel_audit_data"], pinned["pixel_audit_data"])

            with patch("screenshot_observation_loader._require_grid",
                       return_value=(1, 1, [["dark"]], Counter({"dark": 1}))), \
                 patch("game_state.GameState.validate", return_value=[]), \
                 patch.object(Path, "read_text",
                              side_effect=AssertionError("capture path reopened")):
                state, level_audit = load_observed_level(
                    observation_path=board_path,
                    shooter_path=shooter_path,
                    observation_data=result["board_data"],
                    shooter_data=result["shooter_data"],
                )

            self.assertEqual(state.snapshot_id, "sha256:" + "a" * 64)
            self.assertEqual(state.capture_session_id, "session-abc")
            self.assertTrue(level_audit["shooter_capture_provenance_verified"])
            self.assertFalse(level_audit["game_taps_enabled"])


    def test_level_loader_forwards_pinned_objects_without_reopening_paths(self):
        board_data = {"source_sha256": "a" * 64}
        shooter_data = {"visible_shooters": []}
        with patch(
            "screenshot_observation_loader.load_observed_level",
            return_value=("state", {"source": "screenshot_observation"}),
        ) as loader:
            result = load_level(
                observation_path="mutable-board.json",
                shooter_path="mutable-shooters.json",
                observation_data=board_data,
                shooter_data=shooter_data,
            )
        self.assertEqual(result[0], "state")
        self.assertIs(loader.call_args.kwargs["observation_data"], board_data)
        self.assertIs(loader.call_args.kwargs["shooter_data"], shooter_data)


if __name__ == "__main__":
    unittest.main()
