import json
import tempfile
import unittest
from pathlib import Path

from annotation_validator import validate_annotation, load_and_validate


VALID = {
    "annotation_version": "1.0",
    "capture_session_id": "session-test-001",
    "board_snapshot_id": "sha256:" + "a" * 64,
    "annotated_at": "2026-11-26T12:00:00+00:00",
    "annotator": "test-human",
    "human_confirmed": True,
    "shooters": [
        {"id": "s1", "color": "red", "ammo": 10, "slot_index": 0}
    ],
}


class AnnotationValidatorTests(unittest.TestCase):
    def test_valid_annotation_accepted(self):
        ok, errors = validate_annotation(VALID)
        self.assertTrue(ok, errors)
        self.assertEqual(errors, [])

    def test_missing_human_confirmed_rejected(self):
        data = dict(VALID)
        del data["human_confirmed"]
        ok, errors = validate_annotation(data)
        self.assertFalse(ok)
        self.assertTrue(any("human_confirmed" in e for e in errors))

    def test_human_confirmed_false_rejected(self):
        data = dict(VALID)
        data["human_confirmed"] = False
        ok, errors = validate_annotation(data)
        self.assertFalse(ok)
        self.assertTrue(any("human_confirmed" in e for e in errors))

    def test_human_confirmed_string_rejected(self):
        data = dict(VALID)
        data["human_confirmed"] = "true"
        ok, errors = validate_annotation(data)
        self.assertFalse(ok)

    def test_bad_snapshot_rejected(self):
        data = dict(VALID)
        data["board_snapshot_id"] = "not-a-hash"
        ok, errors = validate_annotation(data)
        self.assertFalse(ok)
        self.assertTrue(any("board_snapshot_id" in e for e in errors))

    def test_negative_ammo_rejected(self):
        data = dict(VALID)
        data["shooters"] = [{"id": "s1", "color": "red", "ammo": -1}]
        ok, errors = validate_annotation(data)
        self.assertFalse(ok)
        self.assertTrue(any("ammo" in e for e in errors))

    def test_load_and_validate_raises_on_invalid(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            bad = dict(VALID)
            bad["human_confirmed"] = False
            path.write_text(json.dumps(bad))
            with self.assertRaises(ValueError):
                load_and_validate(path)

    def test_load_and_validate_succeeds_on_valid(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "good.json"
            path.write_text(json.dumps(VALID))
            result = load_and_validate(path)
            self.assertEqual(result["annotator"], "test-human")

    def test_empty_shooters_list_accepted_when_confirmed(self):
        data = dict(VALID)
        data["shooters"] = []
        ok, errors = validate_annotation(data)
        self.assertTrue(ok, errors)

    def test_boolean_ammo_rejected(self):
        data = dict(VALID)
        data["shooters"] = [{"id": "s1", "color": "red", "ammo": True}]
        ok, errors = validate_annotation(data)
        self.assertFalse(ok)
        self.assertTrue(any("ammo" in e for e in errors))

    def test_float_ammo_rejected(self):
        data = dict(VALID)
        data["shooters"] = [{"id": "s1", "color": "red", "ammo": 10.0}]
        ok, errors = validate_annotation(data)
        self.assertFalse(ok)
        self.assertTrue(any("ammo" in e for e in errors))

    def test_naive_timestamp_rejected(self):
        data = dict(VALID)
        data["annotated_at"] = "2026-11-26T12:00:00"
        ok, errors = validate_annotation(data)
        self.assertFalse(ok)
        self.assertTrue(any("annotated_at" in e for e in errors))

    def test_session_id_with_space_rejected(self):
        data = dict(VALID)
        data["capture_session_id"] = "bad session"
        ok, errors = validate_annotation(data)
        self.assertFalse(ok)
        self.assertTrue(any("capture_session_id" in e for e in errors))

    def test_empty_color_rejected(self):
        data = dict(VALID)
        data["shooters"] = [{"id": "s1", "color": "", "ammo": 5}]
        ok, errors = validate_annotation(data)
        self.assertFalse(ok)
        self.assertTrue(any("color" in e for e in errors))

    def test_empty_id_rejected(self):
        data = dict(VALID)
        data["shooters"] = [{"id": "", "color": "red", "ammo": 5}]
        ok, errors = validate_annotation(data)
        self.assertFalse(ok)
        self.assertTrue(any(".id" in e for e in errors))

    def test_extra_fields_tolerated(self):
        data = dict(VALID)
        data["notes"] = "optional note"
        data["shooters"][0]["bonded_ids"] = ["s2"]
        ok, errors = validate_annotation(data)
        self.assertTrue(ok, errors)


if __name__ == "__main__":
    unittest.main()
