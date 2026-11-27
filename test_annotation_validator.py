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

    def test_boolean_ammo_rejected(self):
        data = dict(VALID)
        data["shooters"] = [{"id": "s1", "color": "red", "ammo": True}]
        ok, errors = validate_annotation(data)
        self.assertFalse(ok)
        self.assertTrue(any("ammo" in e for e in errors))

    def test_float_ammo_rejected(self):
        data = dict(VALID)
        data["shooters"] = [{"id": "s1", "color": "red", "ammo": 10.5}]
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

    def test_duplicate_shooter_id_rejected(self):
        data = dict(VALID)
        data["shooters"] = [
            {"id": "s1", "color": "red", "ammo": 10},
            {"id": "s1", "color": "blue", "ammo": 5},
        ]
        ok, errors = validate_annotation(data)
        self.assertFalse(ok)
        self.assertTrue(any("duplicated" in e for e in errors))

    def test_invalid_slot_index_rejected(self):
        data = dict(VALID)
        data["shooters"] = [{"id": "s1", "color": "red", "ammo": 10, "slot_index": 12}]
        ok, errors = validate_annotation(data)
        self.assertFalse(ok)
        self.assertTrue(any("slot_index" in e for e in errors))

    def test_negative_slot_index_rejected(self):
        data = dict(VALID)
        data["shooters"] = [{"id": "s1", "color": "red", "ammo": 10, "slot_index": -1}]
        ok, errors = validate_annotation(data)
        self.assertFalse(ok)

    def test_non_integer_slot_index_rejected(self):
        data = dict(VALID)
        data["shooters"] = [{"id": "s1", "color": "red", "ammo": 10, "slot_index": "0"}]
        ok, errors = validate_annotation(data)
        self.assertFalse(ok)

    def test_self_bonded_id_rejected(self):
        data = dict(VALID)
        data["shooters"] = [{"id": "s1", "color": "red", "ammo": 10, "bonded_ids": ["s1"]}]
        ok, errors = validate_annotation(data)
        self.assertFalse(ok)
        self.assertTrue(any("self-reference" in e for e in errors))

    def test_unknown_bonded_id_rejected(self):
        data = dict(VALID)
        data["shooters"] = [{"id": "s1", "color": "red", "ammo": 10, "bonded_ids": ["missing"]}]
        ok, errors = validate_annotation(data)
        self.assertFalse(ok)
        self.assertTrue(any("unknown id" in e for e in errors))

    def test_asymmetric_bonded_ids_rejected(self):
        data = dict(VALID)
        data["shooters"] = [
            {"id": "s1", "color": "red", "ammo": 10, "bonded_ids": ["s2"]},
            {"id": "s2", "color": "blue", "ammo": 8},
        ]
        ok, errors = validate_annotation(data)
        self.assertFalse(ok)
        self.assertTrue(any("asymmetric bond" in e for e in errors))

    def test_valid_bonded_pair_accepted(self):
        data = dict(VALID)
        data["shooters"] = [
            {"id": "s1", "color": "red", "ammo": 10, "bonded_ids": ["s2"]},
            {"id": "s2", "color": "blue", "ammo": 8, "bonded_ids": ["s1"]},
        ]
        ok, errors = validate_annotation(data)
        self.assertTrue(ok, errors)

    def test_empty_shooters_list_accepted_when_confirmed(self):
        data = dict(VALID)
        data["shooters"] = []
        ok, errors = validate_annotation(data)
        self.assertTrue(ok, errors)

    def test_whitespace_only_id_rejected(self):
        data = dict(VALID)
        data["shooters"] = [{"id": "   ", "color": "red", "ammo": 10}]
        ok, errors = validate_annotation(data)
        self.assertFalse(ok)

    def test_duplicate_slot_index_rejected(self):
        data = dict(VALID)
        data["shooters"] = [
            {"id": "s1", "color": "red", "ammo": 10, "slot_index": 0},
            {"id": "s2", "color": "blue", "ammo": 5, "slot_index": 0},
        ]
        ok, errors = validate_annotation(data)
        self.assertFalse(ok)
        self.assertTrue(any("duplicated" in e and "slot_index" in e for e in errors))

    def test_duplicate_bonded_id_rejected(self):
        data = dict(VALID)
        data["shooters"] = [
            {"id": "s1", "color": "red", "ammo": 10, "bonded_ids": ["s2", "s2"]},
            {"id": "s2", "color": "blue", "ammo": 8},
        ]
        ok, errors = validate_annotation(data)
        self.assertFalse(ok)
        self.assertTrue(any("duplicate" in e and "bonded_ids" in e for e in errors))

    def test_unique_slots_and_bonds_accepted(self):
        data = dict(VALID)
        data["shooters"] = [
            {"id": "s1", "color": "red", "ammo": 10, "slot_index": 0, "bonded_ids": ["s2"]},
            {"id": "s2", "color": "blue", "ammo": 8, "slot_index": 1, "bonded_ids": ["s1"]},
        ]
        ok, errors = validate_annotation(data)
        self.assertTrue(ok, errors)

    def test_notes_string_accepted(self):
        data = dict(VALID)
        data["notes"] = "human observation"
        ok, errors = validate_annotation(data)
        self.assertTrue(ok, errors)

    def test_notes_empty_string_accepted(self):
        data = dict(VALID)
        data["notes"] = ""
        ok, errors = validate_annotation(data)
        self.assertTrue(ok, errors)

    def test_notes_non_string_rejected(self):
        data = dict(VALID)
        data["notes"] = 123
        ok, errors = validate_annotation(data)
        self.assertFalse(ok)
        self.assertTrue(any("notes" in e for e in errors))

    def test_notes_none_rejected(self):
        data = dict(VALID)
        data["notes"] = None
        ok, errors = validate_annotation(data)
        self.assertFalse(ok)
        self.assertTrue(any("notes" in e for e in errors))

    def test_bonded_group_of_three_accepted(self):
        data = dict(VALID)
        data["shooters"] = [
            {"id": "s1", "color": "red", "ammo": 10, "bonded_ids": ["s2", "s3"]},
            {"id": "s2", "color": "blue", "ammo": 8, "bonded_ids": ["s1", "s3"]},
            {"id": "s3", "color": "green", "ammo": 5, "bonded_ids": ["s1", "s2"]},
        ]
        ok, errors = validate_annotation(data)
        self.assertTrue(ok, errors)

    def test_bonded_group_of_four_rejected(self):
        data = dict(VALID)
        data["shooters"] = [
            {"id": "s1", "color": "red", "ammo": 10, "bonded_ids": ["s2"]},
            {"id": "s2", "color": "blue", "ammo": 8, "bonded_ids": ["s1", "s3"]},
            {"id": "s3", "color": "green", "ammo": 5, "bonded_ids": ["s2", "s4"]},
            {"id": "s4", "color": "yellow", "ammo": 3, "bonded_ids": ["s3"]},
        ]
        ok, errors = validate_annotation(data)
        self.assertFalse(ok)
        self.assertTrue(any("maximum 3" in e for e in errors))

if __name__ == "__main__":
    unittest.main()
