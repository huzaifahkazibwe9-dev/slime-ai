import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from shooter_loader import load_shooters


class ShooterLoaderStructureTests(unittest.TestCase):
    def load_payload(self, payload):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "shooters.json"
            path.write_text(json.dumps(payload))
            return load_shooters(path)


    def test_loads_complete_multirow_panel_inventory(self):
        from shooter_loader import load_panel_slots
        slots = []
        for row in range(1, 4):
            for column in range(1, 5):
                slots.append({
                    "id": f"slot_{row}_{column}",
                    "row": row,
                    "column": column,
                    "center": [column * 100, row * 100],
                    "status": "readable" if row == 1 else (
                        "unrevealed" if row == 2 else "partially_occluded"
                    ),
                    "selectable_candidate": False,
                })
        payload = {
            "panel_layout": {"rows": 3, "columns": 4, "slot_count": 12},
            "panel_slots": slots,
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "detection.json"
            path.write_text(json.dumps(payload))
            self.assertEqual(len(load_panel_slots(path)), 12)

    def test_panel_inventory_rejects_duplicate_positions(self):
        from shooter_loader import load_panel_slots
        slot = {
            "id": "A", "row": 1, "column": 1, "center": [10, 10],
            "status": "readable", "selectable_candidate": False,
        }
        payload = {
            "panel_layout": {"rows": 1, "columns": 2, "slot_count": 2},
            "panel_slots": [slot, dict(slot, id="B")],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "detection.json"
            path.write_text(json.dumps(payload))
            with self.assertRaisesRegex(ValueError, "Duplicate panel slot position"):
                load_panel_slots(path)

    def test_panel_inventory_rejects_selectable_unrevealed_slot(self):
        from shooter_loader import load_panel_slots
        payload = {
            "panel_layout": {"rows": 1, "columns": 1, "slot_count": 1},
            "panel_slots": [{
                "id": "hidden", "row": 1, "column": 1, "center": [10, 10],
                "status": "unrevealed", "selectable_candidate": True,
            }],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "detection.json"
            path.write_text(json.dumps(payload))
            with self.assertRaisesRegex(ValueError, "cannot be selectable"):
                load_panel_slots(path)

    def test_panel_inventory_rejects_invalid_image_dimensions(self):
        from shooter_loader import load_panel_slots
        payload = {
            "image_dimensions": [1080, True],
            "panel_layout": {"rows": 1, "columns": 1, "slot_count": 1},
            "panel_slots": [{
                "id": "A", "row": 1, "column": 1, "center": [10, 10],
                "status": "readable", "selectable_candidate": False,
            }],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "detection.json"
            path.write_text(json.dumps(payload))
            with self.assertRaisesRegex(ValueError, "image_dimensions"):
                load_panel_slots(path)

    def test_panel_inventory_rejects_slot_center_outside_image(self):
        from shooter_loader import load_panel_slots
        payload = {
            "image_dimensions": [100, 80],
            "panel_layout": {"rows": 1, "columns": 1, "slot_count": 1},
            "panel_slots": [{
                "id": "A", "row": 1, "column": 1, "center": [100, 40],
                "status": "readable", "selectable_candidate": False,
            }],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "detection.json"
            path.write_text(json.dumps(payload))
            with self.assertRaisesRegex(ValueError, "outside image dimensions"):
                load_panel_slots(path)

    def test_panel_inventory_accepts_in_bounds_slot_center(self):
        from shooter_loader import load_panel_slots
        payload = {
            "image_dimensions": [100, 80],
            "panel_layout": {"rows": 1, "columns": 1, "slot_count": 1},
            "panel_slots": [{
                "id": "A", "row": 1, "column": 1, "center": [99, 79],
                "status": "readable", "selectable_candidate": False,
            }],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "detection.json"
            path.write_text(json.dumps(payload))
            self.assertEqual(len(load_panel_slots(path)), 1)

    def test_panel_inventory_rejects_boolean_dimensions(self):
        from shooter_loader import load_panel_slots
        payload = {
            "panel_layout": {"rows": True, "columns": 1, "slot_count": 1},
            "panel_slots": [],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "detection.json"
            path.write_text(json.dumps(payload))
            with self.assertRaisesRegex(ValueError, "positive integers"):
                load_panel_slots(path)

    def test_rejects_non_object_root(self):
        for payload in ([], None, "invalid"):
            with self.subTest(payload=payload):
                with self.assertRaisesRegex(ValueError, "JSON object"):
                    self.load_payload(payload)

    def test_rejects_non_list_visible_shooters(self):
        for value in (None, {}, "invalid"):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "visible_shooters"):
                    self.load_payload({"visible_shooters": value})

    def test_rejects_non_list_bonded_groups(self):
        for value in (None, {}, "invalid"):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "bonded_groups"):
                    self.load_payload({
                        "visible_shooters": [], "bonded_groups": value
                    })

    def test_rejects_non_list_bonded_group(self):
        with self.assertRaisesRegex(ValueError, "Each bonded group"):
            self.load_payload({
                "visible_shooters": [], "bonded_groups": ["shooter-1"]
            })

    def test_rejects_non_object_shooter_entry(self):
        with self.assertRaisesRegex(ValueError, "must be an object"):
            self.load_payload({"visible_shooters": [None]})

    def test_rejects_invalid_shooter_id(self):
        for value in (None, "", 1):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "invalid id"):
                    self.load_payload({
                        "visible_shooters": [{"id": value}]
                    })


    def test_rejects_duplicate_shooter_ids(self):
        entry = {"id": "shooter-1", "color": {"name": "red"}, "ammo": 1}
        with self.assertRaisesRegex(ValueError, "IDs must be unique"):
            self.load_payload({"visible_shooters": [entry, dict(entry)]})

    def test_rejects_invalid_bonded_group_members(self):
        for group in ([None], [""], [1]):
            with self.subTest(group=group):
                with self.assertRaisesRegex(ValueError, "invalid shooter ID"):
                    self.load_payload({
                        "visible_shooters": [],
                        "bonded_groups": [group],
                    })

    def test_rejects_unknown_bonded_group_members(self):
        with self.assertRaisesRegex(ValueError, "unknown shooters"):
            self.load_payload({
                "visible_shooters": [],
                "bonded_groups": [["missing", "other"]],
            })

    def test_rejects_duplicate_members_in_bonded_group(self):
        with self.assertRaisesRegex(ValueError, "duplicate shooter IDs"):
            self.load_payload({
                "visible_shooters": [
                    {"id": "A", "color": {"name": "red"}, "ammo": 1}
                ],
                "bonded_groups": [["A", "A"]],
            })

    def test_rejects_shooter_in_multiple_bonded_groups(self):
        shooters = [
            {"id": name, "color": {"name": "red"}, "ammo": 1}
            for name in ("A", "B", "C")
        ]
        with self.assertRaisesRegex(ValueError, "multiple bonded groups"):
            self.load_payload({
                "visible_shooters": shooters,
                "bonded_groups": [["A", "B"], ["A", "C"]],
            })

    def test_rejects_bonded_groups_with_fewer_than_two_members(self):
        for group in ([], ["A"]):
            with self.subTest(group=group):
                with self.assertRaisesRegex(ValueError, "at least 2"):
                    self.load_payload({
                        "visible_shooters": [
                            {"id": "A", "color": {"name": "red"}, "ammo": 1}
                        ],
                        "bonded_groups": [group],
                    })

    def test_rejects_bonded_group_larger_than_three(self):
        shooters = [
            {"id": name, "color": {"name": "red"}, "ammo": 1}
            for name in ("A", "B", "C", "D")
        ]
        with self.assertRaisesRegex(ValueError, "maximum size of 3"):
            self.load_payload({
                "visible_shooters": shooters,
                "bonded_groups": [["A", "B", "C", "D"]],
            })

    def test_derives_bonded_ids_from_validated_group_membership(self):
        payload = {
            "visible_shooters": [
                {"id": "A", "color": {"name": "red"}, "ammo": 1,
                 "bonded_ids": ["C"]},
                {"id": "B", "color": {"name": "blue"}, "ammo": 1,
                 "bonded_ids": []},
            ],
            "bonded_groups": [["A", "B"]],
        }
        shooters = self.load_payload(payload)
        self.assertEqual(shooters["A"].bonded_ids, ["B"])
        self.assertEqual(shooters["B"].bonded_ids, ["A"])

    def test_rejects_invalid_colour_record(self):
        for value in (None, {}, {"name": ""}, {"name": 4}):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "invalid colour"):
                    self.load_payload({
                        "visible_shooters": [{"id": "shooter-1", "color": value}]
                    })


    def test_loader_rejects_invalid_ammunition_counts(self):
        for value in (None, True, False, 1.5, -1, "5"):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "non-negative integer ammunition"):
                    self.load_payload({
                        "visible_shooters": [{
                            "id": "A", "color": {"name": "red"}, "ammo": value
                        }],
                        "bonded_groups": [],
                    })

    def test_loader_carries_explicit_unverified_observation_quality(self):
        shooters = self.load_payload({
            "observation_quality": {
                "colour_method": "fixed_panel_sample_hsv_thresholds",
                "ammunition_method": "tesseract_exact_digit_ocr",
                "slot_mapping_method": "fixed_panel_calibration",
                "colour_independently_verified": False,
                "ammunition_independently_verified": False,
                "slot_mapping_independently_verified": False,
            },
            "visible_shooters": [{
                "id": "A", "color": {"name": "red"}, "ammo": 5,
                "ammo_observation_status": "PARSED_EXACT_DIGITS",
                "sample_quality": {"status": "DISTINCT_SAMPLE"},
            }],
            "bonded_groups": [],
        })
        quality = shooters["A"].observation_quality
        self.assertIs(quality["colour_independently_verified"], False)
        self.assertIs(quality["ammunition_independently_verified"], False)
        self.assertIs(quality["slot_mapping_independently_verified"], False)
        self.assertEqual(quality["sample_quality_status"], "DISTINCT_SAMPLE")
        self.assertEqual(
            quality["ammunition_ocr_status"], "PARSED_EXACT_DIGITS"
        )

    def test_modern_detector_record_requires_successful_ammunition_ocr_status(self):
        with self.assertRaisesRegex(ValueError, "not a successful exact-digit parse"):
            self.load_payload({
                "observation_quality": {
                    "ammunition_method": "tesseract_exact_digit_ocr",
                    "ammunition_independently_verified": False,
                },
                "visible_shooters": [
                    {"id": "A", "color": {"name": "red"}, "ammo": 5}
                ],
                "bonded_groups": [],
            })

    def test_modern_detector_record_rejects_value_with_ocr_failure_status(self):
        with self.assertRaisesRegex(ValueError, "not a successful exact-digit parse"):
            self.load_payload({
                "observation_quality": {
                    "ammunition_method": "tesseract_exact_digit_ocr",
                    "ammunition_independently_verified": False,
                },
                "visible_shooters": [{
                    "id": "A", "color": {"name": "red"}, "ammo": 5,
                    "ammo_observation_status": "TESSERACT_TIMEOUT",
                }],
                "bonded_groups": [],
            })

    def test_modern_detector_record_rejects_success_status_without_ammo(self):
        with self.assertRaisesRegex(ValueError, "success status without a valid"):
            self.load_payload({
                "observation_quality": {
                    "ammunition_method": "tesseract_exact_digit_ocr",
                    "ammunition_independently_verified": False,
                },
                "visible_shooters": [{
                    "id": "A", "color": {"name": "red"}, "ammo": None,
                    "ammo_observation_status": "PARSED_EXACT_DIGITS",
                }],
                "bonded_groups": [],
            })

    def test_rejects_unsubstantiated_true_verification_claim(self):
        with self.assertRaisesRegex(ValueError, "without independent validation"):
            self.load_payload({
                "observation_quality": {
                    "colour_independently_verified": True
                },
                "visible_shooters": [
                    {"id": "A", "color": {"name": "red"}, "ammo": 5}
                ],
                "bonded_groups": [],
            })

    def test_legacy_shooter_quality_defaults_to_unverified(self):
        shooters = self.load_payload({
            "visible_shooters": [
                {"id": "A", "color": {"name": "red"}, "ammo": 5}
            ],
            "bonded_groups": [],
        })
        quality = shooters["A"].observation_quality
        self.assertEqual(quality["evidence_source"], "legacy_or_unspecified")
        self.assertIs(quality["colour_independently_verified"], False)
        self.assertIs(quality["ammunition_independently_verified"], False)

    def test_rejects_non_boolean_observation_quality_flag(self):
        with self.assertRaisesRegex(ValueError, "must be a boolean"):
            self.load_payload({
                "observation_quality": {
                    "ammunition_independently_verified": 1
                },
                "visible_shooters": [
                    {"id": "A", "color": {"name": "red"}, "ammo": 5}
                ],
                "bonded_groups": [],
            })

    def test_loader_preserves_each_shooters_ammunition_count(self):
        shooters = self.load_payload({
            "visible_shooters": [
                {"id": "A", "color": {"name": "red"}, "ammo": 3},
                {"id": "B", "color": {"name": "blue"}, "ammo": 11},
            ],
            "bonded_groups": [],
        })
        self.assertEqual(shooters["A"].ammo, 3)
        self.assertEqual(shooters["B"].ammo, 11)

    def test_loader_accepts_zero_ammunition(self):
        shooters = self.load_payload({
            "visible_shooters": [{
                "id": "A", "color": {"name": "red"}, "ammo": 0
            }],
            "bonded_groups": [],
        })
        self.assertEqual(shooters["A"].ammo, 0)

    def test_low_confidence_sample_is_not_loaded_as_shooter(self):
        payload = {
            "visible_shooters": [
                {"id": "clear", "color": {"name": "red"}, "ammo": 5,
                 "sample_quality": {"status": "DISTINCT_SAMPLE"}},
                {"id": "weak", "color": {"name": "blue"}, "ammo": 8,
                 "sample_quality": {"status": "LOW_CONFIDENCE_SAMPLE"}},
            ],
            "bonded_groups": [],
        }
        shooters = self.load_payload(payload)
        self.assertEqual(set(shooters), {"clear"})

    def test_entire_bond_group_is_withheld_when_member_sample_is_weak(self):
        payload = {
            "visible_shooters": [
                {"id": "A", "color": {"name": "red"}, "ammo": 5,
                 "sample_quality": {"status": "DISTINCT_SAMPLE"}},
                {"id": "B", "color": {"name": "blue"}, "ammo": 8,
                 "sample_quality": {"status": "LOW_CONFIDENCE_SAMPLE"}},
            ],
            "bonded_groups": [["A", "B"]],
        }
        shooters = self.load_payload(payload)
        self.assertEqual(shooters, {})

    def test_rejects_unknown_sample_quality_status(self):
        payload = {
            "visible_shooters": [{
                "id": "A", "color": {"name": "red"}, "ammo": 5,
                "sample_quality": {"status": "MAYBE"},
            }],
            "bonded_groups": [],
        }
        with self.assertRaisesRegex(ValueError, "sample quality status"):
            self.load_payload(payload)

    def test_geometry_observations_none_is_accepted(self):
        payload = {
            "visible_shooters": [
                {"id": "A", "color": {"name": "red"}, "ammo": 5}
            ],
            "bonded_groups": [],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "shooters.json"
            path.write_text(json.dumps(payload))
            self.assertEqual(set(load_shooters(path, None)), {"A"})

    def test_rejects_non_object_geometry_observations(self):
        payload = {
            "visible_shooters": [
                {"id": "A", "color": {"name": "red"}, "ammo": 5}
            ],
            "bonded_groups": [],
        }
        for value in ([], ["unexpected"], "invalid", 7):
            with self.subTest(value=value), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "shooters.json"
                path.write_text(json.dumps(payload))
                with self.assertRaisesRegex(ValueError, "geometry_observations must be an object"):
                    load_shooters(path, value)

    def test_legacy_shooter_records_without_sample_quality_still_load(self):
        payload = {
            "visible_shooters": [
                {"id": "A", "color": {"name": "red"}, "ammo": 5}
            ],
            "bonded_groups": [],
        }
        self.assertEqual(set(self.load_payload(payload)), {"A"})



    def test_loader_uses_prevalidated_pinned_data_without_reopening_path(self):
        payload = {
            "visible_shooters": [
                {"id": "A", "color": {"name": "red"}, "ammo": 5}
            ],
            "bonded_groups": [],
        }
        with patch.object(
            Path, "read_text",
            side_effect=AssertionError("pinned shooter data must not reread path"),
        ):
            shooters = load_shooters(
                Path("capture-path-must-not-be-opened.json"),
                data=payload,
            )
        self.assertEqual(set(shooters), {"A"})
        self.assertEqual(shooters["A"].ammo, 5)

    def test_shooter_loader_rejects_duplicate_visible_shooters_key(self):
        payload = (
            '{"visible_shooters":[{"id":"A","color":{"name":"red"},"ammo":5}],'
            '"visible_shooters":[],"bonded_groups":[]}'
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "shooters.json"
            path.write_text(payload)
            with self.assertRaisesRegex(ValueError, "Duplicate JSON object key"):
                load_shooters(path)


if __name__ == "__main__":
    unittest.main(verbosity=2)
