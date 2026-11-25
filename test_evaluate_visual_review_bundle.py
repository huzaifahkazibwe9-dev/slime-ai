import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

import evaluate_visual_review_bundle as combined
from prepare_colour_labels import build_template as build_colour_template
from prepare_shooter_labels import build_template as build_shooter_template


def encoded(data):
    return json.dumps(data, indent=2, sort_keys=True).encode("utf-8")


class CombinedVisualReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.image_path = self.root / "source.png"
        Image.new("RGB", (40, 30), (30, 60, 90)).save(self.image_path)
        self.image_bytes = self.image_path.read_bytes()
        self.image_hash = hashlib.sha256(self.image_bytes).hexdigest()
        self.session = "combined-review-session"
        self.timestamp = "2026-11-25T12:00:00+00:00"

        self.board = {
            "source_sha256": self.image_hash,
            "image_size": [40, 30],
            "grid_size": [2, 2],
            "raw_rgb": [[[30, 60, 90], [31, 61, 91]],
                        [[32, 62, 92], [33, 63, 93]]],
            "capture_session_id": self.session,
            "captured_at": self.timestamp,
            "snapshot_id": "sha256:" + self.image_hash,
            "board_snapshot_id": "sha256:" + self.image_hash,
        }
        self.shooter = self._make_shooter()
        self.board_labels = build_colour_template(self.board)
        self.board_labels["labelled_by_user"] = True
        for index, sample in enumerate(self.board_labels["samples"]):
            sample["label"] = ("cyan", "red", "green", "purple")[index]

        self.detection_bytes = encoded(self.shooter)
        self.shooter_labels = build_shooter_template(
            self.shooter, self.detection_bytes, self.image_bytes
        )
        self.shooter_labels["labelled_by_user"] = True
        for sample in self.shooter_labels["samples"]:
            detector = sample["detector"]
            human = sample["human"]
            sample["review_status"] = "confirmed"
            human["row"] = detector["row"]
            human["column"] = detector["column"]
            if detector["row"] == 1:
                human["visibility"] = "visible"
                human["colour"] = "cyan"
                human["ammunition_readable"] = True
                human["ammunition"] = 40
            elif detector["row"] == 2:
                human["visibility"] = "unrevealed"
                human["ammunition_readable"] = False
            else:
                human["visibility"] = "partially_occluded"
                human["ammunition_readable"] = False

        self.board_path = self.root / "board.json"
        self.shooter_path = self.root / "detection.json"
        self.audit_path = self.root / "audit.json"
        self.board_labels_path = self.root / "board-labels.json"
        self.shooter_labels_path = self.root / "shooter-labels.json"
        self.manifest_path = self.root / "manifest.json"
        self._write_sources_and_reviews()
        self._write_manifest()

    def tearDown(self):
        self.tmp.cleanup()

    def _make_shooter(self):
        slots, observations = [], []
        for row in range(1, 4):
            for column in range(1, 5):
                slot_id = f"r{row}c{column}"
                slot_status, observation_status = {
                    1: ("readable", "readable_candidate"),
                    2: ("unrevealed", "unrevealed_candidate"),
                    3: ("partially_occluded", "partially_occluded_candidate"),
                }[row]
                x, y = (column - 1) * 10, (row - 1) * 10
                slots.append({
                    "id": slot_id, "row": row, "column": column,
                    "status": slot_status, "selectable_candidate": False,
                })
                observations.append({
                    "id": slot_id, "row": row, "column": column,
                    "status": observation_status, "selectable_candidate": False,
                    "verified": False, "color_observation": {"name": "cyan"},
                    "ammunition_observation": 40 if row == 1 else None,
                    "ammunition_observation_status": (
                        "PARSED_EXACT_DIGITS" if row == 1
                        else "NOT_ATTEMPTED_UNVERIFIED_SLOT"
                    ),
                    "screen_center": [x + 5, y + 5],
                    "screen_sample": [x + 5, y + 5],
                    "screen_box": [x, y, x + 10, y + 10],
                    "sample_quality": {"status": "DISTINCT_SAMPLE"},
                })
        return {
            "image_dimensions": [40, 30],
            "panel_layout": {"rows": 3, "columns": 4, "slot_count": 12},
            "panel_slots": slots,
            "panel_slot_observations": observations,
            "observation_quality": {
                "colour_independently_verified": False,
                "ammunition_independently_verified": False,
                "slot_mapping_independently_verified": False,
            },
            "capture_provenance": {
                "verified": True, "source_sha256": self.image_hash,
                "capture_config_sha256": "a" * 64,
                "capture_session_id": self.session, "captured_at": self.timestamp,
                "panel_bounds": [0, 0, 40, 30],
            },
        }

    def _audit_report(self):
        return {
            "source_sha256": self.image_hash,
            "image_size": [40, 30], "grid_size": [2, 2],
            "pixel_samples_reproduced": True,
            "extraction_fingerprint_match": True,
            "label_mismatch_count": 0, "colour_counts_match": True,
        }

    def _write_sources_and_reviews(self):
        self.board_path.write_bytes(encoded(self.board))
        self.shooter_path.write_bytes(self.detection_bytes)
        audit = self._audit_report()
        audit.update({
            "capture_session_id": self.session,
            "captured_at": self.timestamp,
            "snapshot_id": "sha256:" + self.image_hash,
            "board_snapshot_id": "sha256:" + self.image_hash,
        })
        self.audit_path.write_bytes(encoded(audit))
        self.board_labels_path.write_bytes(encoded(self.board_labels))
        self.shooter_labels_path.write_bytes(encoded(self.shooter_labels))

    def _write_manifest(self):
        blank_board = build_colour_template(self.board)
        blank_shooter = build_shooter_template(
            self.shooter, self.detection_bytes, self.image_bytes
        )
        manifest = {
            "schema_version": 1,
            "review_status": "NOT_REVIEWED",
            "labelled_by_user": False,
            "source_screenshot_sha256": self.image_hash,
            "source_screenshot_size": [40, 30],
            "capture_session_id": self.session,
            "captured_at": self.timestamp,
            "source_artifacts_sha256": {
                "board_observation_json": hashlib.sha256(self.board_path.read_bytes()).hexdigest(),
                "shooter_detection_json": hashlib.sha256(self.shooter_path.read_bytes()).hexdigest(),
                "source_pixel_audit_json": hashlib.sha256(self.audit_path.read_bytes()).hexdigest(),
            },
            "review_templates": {
                "board_colour": {
                    "file": self.board_labels_path.name,
                    "sha256": hashlib.sha256(encoded(blank_board)).hexdigest(),
                    "sample_count": 4,
                },
                "shooter_observation": {
                    "file": self.shooter_labels_path.name,
                    "sha256": hashlib.sha256(encoded(blank_shooter)).hexdigest(),
                    "sample_count": 12,
                },
            },
            "limitations": ["Synthetic fixture only"],
        }
        manifest["bundle_sha256"] = hashlib.sha256(encoded(manifest)).hexdigest()
        self.manifest_path.write_bytes(encoded(manifest))

    def _reseal_manifest(self, mutate):
        manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        mutate(manifest)
        manifest.pop("bundle_sha256", None)
        manifest["bundle_sha256"] = hashlib.sha256(encoded(manifest)).hexdigest()
        self.manifest_path.write_bytes(encoded(manifest))

    def _evaluate(self):
        return combined.evaluate_visual_review_bundle(
            self.manifest_path, self.board_labels_path, self.shooter_labels_path,
            self.board_path, self.shooter_path, self.audit_path, self.image_path,
        )

    def test_valid_bundle_evaluates_both_review_sets(self):
        with patch.object(combined, "audit_source_pixels", return_value=self._audit_report()):
            report = self._evaluate()
        self.assertTrue(report["review_bundle_verified"])
        self.assertEqual(report["board_colour_evaluation"]["sample_count"], 4)
        self.assertEqual(report["shooter_observation_evaluation"]["confirmed_sample_count"], 12)
        self.assertTrue(report["source_verification"]["reviewed_board_rgb_matches_source_observation"])
        self.assertEqual(
            report["review_artifacts_sha256"]["manifest_json"],
            hashlib.sha256(self.manifest_path.read_bytes()).hexdigest(),
        )
        self.assertEqual(
            report["review_artifacts_sha256"]["board_labels_json"],
            hashlib.sha256(self.board_labels_path.read_bytes()).hexdigest(),
        )
        self.assertEqual(
            report["review_artifacts_sha256"]["shooter_labels_json"],
            hashlib.sha256(self.shooter_labels_path.read_bytes()).hexdigest(),
        )
        expected_source_hashes = {
            "board_observation_json": hashlib.sha256(self.board_path.read_bytes()).hexdigest(),
            "shooter_detection_json": hashlib.sha256(self.shooter_path.read_bytes()).hexdigest(),
            "source_pixel_audit_json": hashlib.sha256(self.audit_path.read_bytes()).hexdigest(),
            "source_screenshot": hashlib.sha256(self.image_path.read_bytes()).hexdigest(),
        }
        self.assertEqual(report["source_artifacts_sha256"], expected_source_hashes)
        self.assertFalse(report["gameplay_verified"])
        self.assertFalse(report["label_truth_independently_verified"])

    def test_rejects_modified_manifest_content(self):
        manifest = json.loads(self.manifest_path.read_text())
        manifest["capture_session_id"] = "changed"
        self.manifest_path.write_bytes(encoded(manifest))
        with self.assertRaisesRegex(ValueError, "bundle_sha256"):
            self._evaluate()

    def test_rejects_board_rgb_changed_after_template_creation(self):
        self.board_labels["samples"][0]["rgb"] = [255, 0, 255]
        self.board_labels_path.write_bytes(encoded(self.board_labels))
        with patch.object(combined, "audit_source_pixels", return_value=self._audit_report()):
            with self.assertRaisesRegex(ValueError, "differs from source observation"):
                self._evaluate()

    def test_rejects_source_artifact_replacement(self):
        self.board["raw_rgb"][0][0] = [99, 98, 97]
        self.board_path.write_bytes(encoded(self.board))
        with patch.object(combined, "audit_source_pixels", return_value=self._audit_report()):
            with self.assertRaisesRegex(ValueError, "source artifact hashes"):
                self._evaluate()

    def test_rejects_board_template_metadata_change(self):
        self.board_labels["unapproved_metadata"] = "changed"
        self.board_labels_path.write_bytes(encoded(self.board_labels))
        with patch.object(combined, "audit_source_pixels", return_value=self._audit_report()):
            with self.assertRaisesRegex(ValueError, "metadata changed outside human label fields"):
                self._evaluate()

    def test_rejects_unknown_top_level_manifest_field_even_when_resealed(self):
        self._reseal_manifest(
            lambda manifest: manifest.update({"untrusted_extension": "unexpected"})
        )
        with self.assertRaisesRegex(ValueError, "fields do not match schema-v1"):
            self._evaluate()

    def test_rejects_unknown_source_artifact_hash_field_even_when_resealed(self):
        self._reseal_manifest(
            lambda manifest: manifest["source_artifacts_sha256"].update(
                {"untrusted_source": "a" * 64}
            )
        )
        with self.assertRaisesRegex(ValueError, "source_artifacts_sha256 fields"):
            self._evaluate()

    def test_rejects_unknown_review_template_record_even_when_resealed(self):
        self._reseal_manifest(
            lambda manifest: manifest["review_templates"].update(
                {"untrusted_template": {}}
            )
        )
        with self.assertRaisesRegex(ValueError, "review_templates fields"):
            self._evaluate()

    def test_rejects_extra_template_entry_field_even_when_resealed(self):
        self._reseal_manifest(
            lambda manifest: manifest["review_templates"]["board_colour"].update(
                {"untrusted_note": "unexpected"}
            )
        )
        with self.assertRaisesRegex(ValueError, "board_colour template fields"):
            self._evaluate()

    def test_rejects_invalid_capture_session_id_even_when_resealed(self):
        self._reseal_manifest(
            lambda manifest: manifest.update({"capture_session_id": "../invalid"})
        )
        with self.assertRaisesRegex(ValueError, "capture_session_id is invalid"):
            self._evaluate()

    def test_rejects_timezone_naive_manifest_timestamp_even_when_resealed(self):
        self._reseal_manifest(
            lambda manifest: manifest.update({"captured_at": "2026-11-25T12:00:00"})
        )
        with self.assertRaisesRegex(ValueError, "canonical ISO-8601 with a UTC offset"):
            self._evaluate()

    def test_rejects_noncanonical_manifest_timestamp_even_when_resealed(self):
        self._reseal_manifest(
            lambda manifest: manifest.update({"captured_at": "2026-11-25T12:00:00Z"})
        )
        with self.assertRaisesRegex(ValueError, "canonical ISO-8601 with a UTC offset"):
            self._evaluate()

    def test_rejects_invalid_manifest_limitations_even_when_resealed(self):
        self._reseal_manifest(
            lambda manifest: manifest.update({"limitations": ["", 12]})
        )
        with self.assertRaisesRegex(ValueError, "limitations must be a non-empty list"):
            self._evaluate()

    def test_rejects_manifest_template_baseline_hash_mismatch(self):
        manifest = json.loads(self.manifest_path.read_text())
        manifest["review_templates"]["board_colour"]["sha256"] = "b" * 64
        manifest.pop("bundle_sha256")
        manifest["bundle_sha256"] = hashlib.sha256(encoded(manifest)).hexdigest()
        self.manifest_path.write_bytes(encoded(manifest))
        with patch.object(combined, "audit_source_pixels", return_value=self._audit_report()):
            with self.assertRaisesRegex(ValueError, "Manifest board template hash"):
                self._evaluate()

    def test_rejects_board_shooter_session_mismatch(self):
        self.shooter["capture_provenance"]["capture_session_id"] = "other-session"
        self.detection_bytes = encoded(self.shooter)
        self.shooter_path.write_bytes(self.detection_bytes)
        self._write_manifest()
        with self.assertRaisesRegex(ValueError, "Shooter detection capture identity"):
            self._evaluate()


if __name__ == "__main__":
    unittest.main()
