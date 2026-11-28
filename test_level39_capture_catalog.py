"""Offline tests for the supplied Level 39 filename-clock catalog.

These tests check the supplied notes and the fail-closed contract. They do
not require image bytes and must not satisfy the private Level 39 skips.
"""

import unittest
from pathlib import Path

import level39_capture_catalog as catalog_mod
from level39_capture_catalog import (
    MISSING_OBSERVATIONS,
    catalog_is_planning_eligible,
    level39_capture_catalog,
    link_sessions,
    transfer_annotation_labels,
    validate_level39_catalog,
)


class Level39FilenameCatalogTests(unittest.TestCase):
    def setUp(self):
        self.catalog = level39_capture_catalog()

    def test_canonical_catalog_has_no_contract_errors(self):
        self.assertEqual(validate_level39_catalog(self.catalog), [])

    def test_sessions_stay_separate_and_dated(self):
        nov21 = self.catalog["november_21"]
        nov27 = self.catalog["november_27"]
        self.assertEqual(nov21["calendar_date"], "2026-11-21")
        self.assertEqual(nov27["calendar_date"], "2026-11-27")
        self.assertNotEqual(nov21["session_id"], nov27["session_id"])
        self.assertEqual(nov27["separate_from_session_id"], nov21["session_id"])
        self.assertEqual(self.catalog["session_relationship"]["status"], "unestablished")
        self.assertIsNone(self.catalog["session_relationship"]["established_by"])

    def test_november_21_conveyor_notes_follow_filename_clock(self):
        captures = self.catalog["november_21"]["captures"]
        self.assertEqual(
            [item["filename"] for item in captures],
            [
                "Screenshot_20261121-092542_Slime Loop.jpg",
                "Screenshot_20261121-092544_Slime Loop.jpg",
                "Screenshot_20261121-092548_Slime Loop.jpg",
                "Screenshot_20261121-092554_Slime Loop.jpg",
            ],
        )
        self.assertEqual(
            [item["filename_clock"]["text"] for item in captures],
            ["09:25:42", "09:25:44", "09:25:48", "09:25:54"],
        )
        self.assertEqual(
            [item["conveyor_side_visible"] for item in captures],
            ["bottom", "right", "top", "left"],
        )
        self.assertIsNone(self.catalog["rotation_model"])
        self.assertFalse(self.catalog["november_21"]["pixel_identity_rechecked"])

    def test_november_27_popup_order_and_clear_board_note(self):
        captures = self.catalog["november_27"]["captures"]
        self.assertEqual(
            [item["filename_clock"]["text"] for item in captures],
            ["17:39:51", "17:39:59", "17:40:12", "17:40:20", "17:40:41"],
        )
        self.assertEqual(
            [None if item["popup"] is None else item["popup"]["display_name"] for item in captures],
            ["Extra Tray", "Magic Glove", "Angel Slime", "Dragon Roar", None],
        )
        last = captures[-1]
        self.assertEqual(last["board_visibility_note"], "clear_board")
        self.assertEqual(last["conveyor_side_visible"], "top")
        self.assertIsNone(last["popup"])

    def test_no_timezone_ammo_pixels_or_raw_shooter_labels(self):
        for session in (self.catalog["november_21"], self.catalog["november_27"]):
            self.assertFalse(session["timezone_identified"])
            self.assertIsNone(session["utc_offset"])
            for capture in session["captures"]:
                self.assertIsNone(capture["utc_offset"])
                self.assertFalse(capture["timezone_identified"])
                self.assertIsNone(capture["filename_clock"]["utc_offset"])
                self.assertIsNone(capture["ammunition"])
                self.assertIsNone(capture["pixel_colours"])
                self.assertIsNone(capture["shooter_labels"])
                self.assertFalse(capture["bytes_attached"])
                self.assertIsNone(capture["image_sha256"])

    def test_popups_do_not_record_prices_or_authorize_purchase(self):
        popups = [
            capture["popup"]
            for capture in self.catalog["november_27"]["captures"]
            if capture["popup"] is not None
        ]
        self.assertEqual(len(popups), 4)
        for popup in popups:
            self.assertEqual(popup["kind"], "shop_popup")
            self.assertIsNone(popup["displayed_price"])
            self.assertIsNone(popup["displayed_charge"])
            self.assertFalse(popup["price_transcribed"])
            self.assertFalse(popup["purchase_authorized"])
            self.assertFalse(popup["game_action_performed"])

    def test_annotated_reference_is_not_a_raw_capture(self):
        annotated = self.catalog["annotated_reference"]
        self.assertEqual(annotated["filename"], "shooter_positions_marked.jpg")
        self.assertEqual(annotated["role"], "annotated_reference")
        self.assertFalse(annotated["untouched_original"])
        self.assertFalse(annotated["copy_labels_onto_raw_captures"])
        self.assertEqual(
            annotated["annotation_marks"],
            ("red_marks", "top_1", "top_2", "top_3", "top_4"),
        )
        raw_names = [
            capture["filename"]
            for session in (self.catalog["november_21"], self.catalog["november_27"])
            for capture in session["captures"]
        ]
        self.assertNotIn(annotated["filename"], raw_names)

    def test_missing_observations_stay_listed(self):
        self.assertIn("image bytes and sha256 for every listed file", MISSING_OBSERVATIONS)
        self.assertIn(
            "UTC offset or EXIF OffsetTimeOriginal (filename clock only; timezone not identified)",
            MISSING_OBSERVATIONS,
        )
        self.assertIn("pixel colours and board grid contents", MISSING_OBSERVATIONS)
        self.assertIn(
            "shooter positions and ammunition counts on the unmarked screenshots",
            MISSING_OBSERVATIONS,
        )
        self.assertEqual(self.catalog["missing_observations"], MISSING_OBSERVATIONS)

    def test_safety_flags_stay_closed(self):
        safety = self.catalog["safety"]
        self.assertFalse(safety["game_taps_enabled"])
        self.assertFalse(safety["planning_authorized"])
        self.assertFalse(safety["purchase_authorized"])
        self.assertFalse(safety["conveyor_mechanics_validated"])
        self.assertFalse(safety["colour_classification_validated"])
        self.assertFalse(safety["solver_correctness_validated"])
        self.assertFalse(safety["pixel_comparison_performed"])
        self.assertFalse(safety["sessions_same_capture"])
        self.assertFalse(self.catalog["private_level39_fixtures_replaced"])
        self.assertFalse(catalog_is_planning_eligible(self.catalog))

    def test_link_and_label_transfer_are_refused(self):
        linked = link_sessions({"method": "caller_assertion", "same": True})
        self.assertFalse(linked["linked"])
        self.assertEqual(linked["reason"], "NOT_ESTABLISHED_BY_THIS_CATALOG")
        self.assertFalse(linked["planning_authorized"])
        self.assertFalse(linked["purchase_authorized"])
        self.assertFalse(linked["game_taps_enabled"])

        refused = transfer_annotation_labels(
            "Screenshot_20261121-092542_Slime Loop.jpg",
            ["top_1", "top_2", "top_3", "top_4"],
        )
        self.assertFalse(refused["applied"])
        self.assertEqual(refused["labels_not_copied"], ["top_1", "top_2", "top_3", "top_4"])
        self.assertFalse(refused["planning_authorized"])

    def test_invented_offset_ammo_price_or_merge_fails_closed(self):
        cases = []

        offset = level39_capture_catalog()
        offset["november_21"]["utc_offset"] = "+03:00"
        cases.append(offset)

        ammo = level39_capture_catalog()
        ammo["november_21"]["captures"][0]["ammunition"] = 38
        cases.append(ammo)

        pixels = level39_capture_catalog()
        pixels["november_27"]["captures"][-1]["pixel_colours"] = ["white"]
        cases.append(pixels)

        labels = level39_capture_catalog()
        labels["november_21"]["captures"][0]["shooter_labels"] = ["top_1"]
        cases.append(labels)

        price = level39_capture_catalog()
        price["november_27"]["captures"][0]["popup"]["displayed_price"] = 40
        cases.append(price)

        purchase = level39_capture_catalog()
        purchase["safety"]["purchase_authorized"] = True
        cases.append(purchase)

        taps = level39_capture_catalog()
        taps["safety"]["game_taps_enabled"] = True
        cases.append(taps)

        same = level39_capture_catalog()
        same["session_relationship"] = {"status": "same_capture", "established_by": "guess"}
        cases.append(same)

        rotation = level39_capture_catalog()
        rotation["rotation_model"] = "clockwise"
        cases.append(rotation)

        for mutated in cases:
            self.assertTrue(validate_level39_catalog(mutated), mutated)

    def test_reordered_filename_clock_is_rejected(self):
        mutated = level39_capture_catalog()
        captures = mutated["november_21"]["captures"]
        captures[0], captures[1] = captures[1], captures[0]
        errors = validate_level39_catalog(mutated)
        self.assertTrue(any("ascending" in error for error in errors))

    def test_catalog_construction_does_not_share_mutable_state(self):
        first = level39_capture_catalog()
        first["november_21"]["captures"][0]["ammunition"] = 1
        second = level39_capture_catalog()
        self.assertIsNone(second["november_21"]["captures"][0]["ammunition"])
        self.assertEqual(validate_level39_catalog(second), [])

    def test_module_does_not_name_private_fixture_files(self):
        source = Path(catalog_mod.__file__).read_text(encoding="utf-8")
        for banned in (
            "vision_level39.json",
            "conveyor_timeline.json",
            "conveyor_visual_observations.json",
            "shooter_detection.json",
            "color_matches.json",
        ):
            self.assertNotIn(banned, source)


if __name__ == "__main__":
    unittest.main()
