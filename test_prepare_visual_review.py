import hashlib, json, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
import prepare_visual_review as review


class VisualReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.image = self.root / "source.png"
        Image.new("RGB", (40, 30), (80, 120, 160)).save(self.image)
        self.digest = hashlib.sha256(self.image.read_bytes()).hexdigest()
        self.session = "review-session"
        self.time = "2026-11-25T12:00:00+00:00"
        review.BOARD_OUTPUT = self.root / "board.json"
        review.SHOOTER_OUTPUT = self.root / "shooter.json"
        review.PIXEL_AUDIT_OUTPUT = self.root / "audit.json"
        self.board = {
            "source_sha256": self.digest, "image_size": [40, 30],
            "grid_size": [2, 2], "raw_rgb": [[[1, 2, 3], [4, 5, 6]], [[7, 8, 9], [10, 11, 12]]],
            "capture_session_id": self.session, "captured_at": self.time,
            "snapshot_id": "sha256:" + self.digest, "board_snapshot_id": "sha256:" + self.digest,
        }
        self.audit = {
            "source_sha256": self.digest, "pixel_samples_reproduced": True,
            "extraction_fingerprint_match": True, "label_mismatch_count": 0,
            "colour_counts_match": True, "capture_session_id": self.session,
            "captured_at": self.time, "snapshot_id": "sha256:" + self.digest,
            "source_image_hash_checked": True,
            "source_image_dimensions_checked": True,
            "label_truth_independently_verified": False,
            "calibration_alignment_verified": False,
            "gameplay_verified": False,
            "game_taps_enabled": False,
            "board_snapshot_id": "sha256:" + self.digest,
        }
        slots, obs = [], []
        for row in range(1, 4):
            for col in range(1, 5):
                sid = f"r{row}c{col}"
                ss, os = {1: ("readable", "readable_candidate"), 2: ("unrevealed", "unrevealed_candidate"), 3: ("partially_occluded", "partially_occluded_candidate")}[row]
                x, y = (col - 1) * 10, (row - 1) * 10
                slots.append({"id": sid, "row": row, "column": col, "status": ss, "selectable_candidate": False})
                obs.append({
                    "id": sid, "row": row, "column": col, "status": os,
                    "selectable_candidate": False, "verified": False,
                    "color_observation": {"name": "cyan"},
                    "ammunition_observation": 40 if row == 1 else None,
                    "ammunition_observation_status": "PARSED_EXACT_DIGITS" if row == 1 else "NOT_ATTEMPTED_UNVERIFIED_SLOT",
                    "screen_center": [x + 5, y + 5], "screen_sample": [x + 5, y + 5],
                    "screen_box": [x, y, x + 10, y + 10],
                    "sample_quality": {"status": "DISTINCT_SAMPLE"},
                })
        self.shooter = {
            "image_dimensions": [40, 30], "panel_layout": {"rows": 3, "columns": 4, "slot_count": 12},
            "panel_slots": slots, "panel_slot_observations": obs,
            "observation_quality": {"colour_independently_verified": False, "ammunition_independently_verified": False, "slot_mapping_independently_verified": False},
            "capture_provenance": {"verified": True, "source_sha256": self.digest, "capture_config_sha256": "a" * 64, "capture_session_id": self.session, "captured_at": self.time, "panel_bounds": [0, 0, 40, 30]},
        }
        self._write()

    def tearDown(self):
        self.tmp.cleanup()

    def _write(self):
        review.BOARD_OUTPUT.write_text(json.dumps(self.board))
        review.SHOOTER_OUTPUT.write_text(json.dumps(self.shooter))
        review.PIXEL_AUDIT_OUTPUT.write_text(json.dumps(self.audit))

    def _pipeline(self, *_):
        return self.audit

    def _run(self):
        with patch.object(review, "run_capture_pipeline", side_effect=self._pipeline):
            return review.prepare_visual_review_bundle(
                self.image, self.root / "config.json", self.root / "board-labels.json",
                self.root / "shooter-labels.json", self.root / "manifest.json",
            )

    def test_templates_are_blank_and_share_source_hash(self):
        manifest = self._run()
        board = json.loads((self.root / "board-labels.json").read_text())
        shooter = json.loads((self.root / "shooter-labels.json").read_text())
        self.assertEqual(board["source_sha256"], self.digest)
        self.assertEqual(shooter["source_screenshot_sha256"], self.digest)
        self.assertEqual((len(board["samples"]), len(shooter["samples"])), (4, 12))
        self.assertFalse(board["labelled_by_user"])
        self.assertFalse(shooter["labelled_by_user"])
        self.assertEqual(manifest["review_status"], "NOT_REVIEWED")
        self.assertTrue((self.root / "manifest.json").is_file())

    def test_rejects_capture_audit_claiming_gameplay_verified(self):
        self.audit["gameplay_verified"] = True
        self._write()
        with self.assertRaisesRegex(ValueError, "gameplay_verified"):
            self._run()

    def test_rejects_persisted_audit_missing_calibration_status(self):
        self.audit.pop("calibration_alignment_verified")
        self._write()
        with self.assertRaisesRegex(ValueError, "calibration_alignment_verified"):
            self._run()

    def test_rejects_screenshot_replaced_after_capture(self):
        def replace(*args):
            report = self._pipeline(*args)
            Image.new("RGB", (40, 30), (1, 2, 3)).save(self.image)
            return report
        with patch.object(review, "run_capture_pipeline", side_effect=replace):
            with self.assertRaisesRegex(ValueError, "changed after"):
                review.prepare_visual_review_bundle(
                    self.image, self.root / "config.json", self.root / "b.json",
                    self.root / "s.json", self.root / "m.json",
                )

    def test_rejects_mismatched_board_shooter_session(self):
        self.shooter["capture_provenance"]["capture_session_id"] = "wrong"
        self._write()
        with self.assertRaisesRegex(ValueError, "different session IDs"):
            self._run()


if __name__ == "__main__":
    unittest.main()
