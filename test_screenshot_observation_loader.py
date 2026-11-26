import json
import runpy
import sys
from contextlib import redirect_stdout
from io import BytesIO, StringIO
from unittest.mock import patch
import tempfile
import unittest
from pathlib import Path

from screenshot_observation_loader import load_observed_level
from screenshot_observation_loader import verify_source_samples, _require_grid

from level_loader import load_level
from execution_engine import run_dry_simulation, run_multi_batch_schedule


class ScreenshotObservationLoaderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.observation_path = self.root / "observation.json"
        self.shooter_path = self.root / "shooters.json"
        board = [
            ["cyan", "white", "cyan"],
            ["orange", "pink", "white"],
        ]
        rgb = [
            [[10, 180, 230], [245, 245, 245], [10, 180, 230]],
            [[200, 120, 60], [240, 80, 220], [245, 245, 245]],
        ]
        self.observation = {
            "image_size": [300, 200],
            "grid_size": [3, 2],
            "bounds": [10, 10, 290, 190],
            "board": board,
            "raw_rgb": rgb,
            "counts": {"cyan": 2, "white": 2, "orange": 1, "pink": 1},
            "source_sha256": "a" * 64,
            "capture_session_id": "session-test-1",
            "captured_at": "2026-11-23T12:30:00+03:00",
            "snapshot_id": "sha256:" + "a" * 64,
            "board_snapshot_id": "sha256:" + "a" * 64,
            "board_snapshot_id": "sha256:" + "a" * 64,
            "same_board_state_confirmed": False,
            "gameplay_verified": False,
            "vision_classification_verified": False,
            "game_taps_enabled": False,
        }
        self.shooters = {
            "visible_shooters": [
                {
                    "id": "top_1", "color": {"name": "white"},
                    "ammo": 40, "screen_center": [50, 20],
                    "screen_box": [10, 5, 90, 35],
                    "bonded_ids": ["top_2"], "verified": False,
                },
                {
                    "id": "top_2", "color": {"name": "cyan"},
                    "ammo": 40, "screen_center": [150, 20],
                    "screen_box": [110, 5, 190, 35],
                    "bonded_ids": ["top_1"], "verified": False,
                },
            ],
            "bonded_groups": [["top_1", "top_2"]],
            "capture_provenance": {
                "verified": False,
                "source_sha256": None,
                "capture_session_id": None,
                "captured_at": None,
            },
        }
        self.write()

    def tearDown(self):
        self.temp.cleanup()

    def write(self):
        self.observation_path.write_text(json.dumps(self.observation))
        self.shooter_path.write_text(json.dumps(self.shooters))

    def test_direct_loader_rejects_overlapping_3x3_sample_windows(self):
        invalid = dict(self.observation)
        invalid["grid_size"] = [5, 2]
        invalid["bounds"] = [10, 10, 20, 190]
        invalid["board"] = [["white"] * 5 for _ in range(2)]
        invalid["raw_rgb"] = [
            [[245, 245, 245] for _ in range(5)]
            for _ in range(2)
        ]
        invalid["counts"] = {"white": 10}
        with self.assertRaisesRegex(ValueError, "overlapping 3x3"):
            _require_grid(invalid)

    def test_direct_loader_rejects_rounded_sample_window_outside_image(self):
        invalid = dict(self.observation)
        invalid["grid_size"] = [1, 1]
        invalid["bounds"] = [298.6, 20, 299, 40]
        invalid["board"] = [["white"]]
        invalid["raw_rgb"] = [[[245, 245, 245]]]
        invalid["counts"] = {"white": 1}
        with self.assertRaisesRegex(ValueError, "outside the screenshot"):
            _require_grid(invalid)

    def test_source_sample_verifier_rejects_overlapping_sampling_windows(self):
        from PIL import Image
        import hashlib

        buffer = BytesIO()
        Image.new("RGB", (300, 200), (245, 245, 245)).save(
            buffer, format="PNG"
        )
        source_bytes = buffer.getvalue()
        invalid = dict(self.observation)
        invalid["source_sha256"] = hashlib.sha256(source_bytes).hexdigest()
        invalid["grid_size"] = [5, 2]
        invalid["bounds"] = [10, 10, 20, 190]
        invalid["sample_centres"] = {
            "x": [11, 13, 15, 17, 19],
            "y": [55, 145],
        }
        invalid["raw_rgb"] = [
            [[245, 245, 245] for _ in range(5)]
            for _ in range(2)
        ]
        with self.assertRaisesRegex(ValueError, "overlapping 3x3"):
            verify_source_samples(invalid, source_bytes)

    def test_direct_loader_requires_same_board_state_to_remain_unverified(self):
        for replacement in (True, None):
            with self.subTest(replacement=replacement):
                invalid = dict(self.observation)
                if replacement is None:
                    del invalid["same_board_state_confirmed"]
                else:
                    invalid["same_board_state_confirmed"] = replacement
                with self.assertRaisesRegex(
                    ValueError, "same_board_state_confirmed"
                ):
                    load_observed_level(
                        self.observation_path,
                        self.shooter_path,
                        observation_data=invalid,
                        shooter_data=self.shooters,
                    )

    def test_direct_loader_rejects_boolean_and_float_colour_counts(self):
        for invalid_count in (True, 2.0):
            with self.subTest(invalid_count=invalid_count):
                invalid = dict(self.observation)
                invalid["counts"] = dict(self.observation["counts"])
                invalid["counts"]["white"] = invalid_count
                with self.assertRaisesRegex(
                    ValueError, "colour counts"
                ):
                    _require_grid(invalid)

    def test_direct_loader_requires_lowercase_sha256_hex(self):
        invalid = dict(self.observation)
        invalid["source_sha256"] = "A" * 64
        invalid["snapshot_id"] = "sha256:" + "A" * 64
        invalid["board_snapshot_id"] = "sha256:" + "A" * 64
        with self.assertRaisesRegex(ValueError, "snapshot identity"):
            _require_grid(invalid)

    def test_observation_integrates_with_shooter_panel(self):
        state, audit = load_observed_level(
            self.observation_path, self.shooter_path, level=39
        )
        self.assertEqual(state.board, self.observation["board"])
        self.assertEqual(state.width, 3)
        self.assertEqual(state.height, 2)
        self.assertEqual(state.remaining_pixels, 6)
        self.assertEqual(len(state.shooters), 2)
        self.assertEqual(state.shooters["top_1"].bonded_ids, ["top_2"])
        self.assertEqual(state.shooters["top_1"].panel_center, (50, 20))
        self.assertIsNone(state.shooters["top_1"].screen_center)
        self.assertFalse(state.shooters["top_1"].accessible)
        self.assertEqual(state.validate(), [])
        self.assertEqual(audit["snapshot_id"], self.observation["snapshot_id"])
        self.assertEqual(state.snapshot_id, self.observation["snapshot_id"])
        self.assertEqual(
            self.observation["board_snapshot_id"],
            self.observation["snapshot_id"],
        )
        self.assertFalse(state.timestamp_identified)

    def test_level_audit_carries_unverified_shooter_quality_flags(self):
        self.shooters["observation_quality"] = {
            "colour_independently_verified": False,
            "ammunition_independently_verified": False,
            "slot_mapping_independently_verified": False,
        }
        for shooter in self.shooters["visible_shooters"]:
            shooter["ammo_observation_status"] = "PARSED_EXACT_DIGITS"
        self.write()
        state, audit = load_observed_level(
            self.observation_path, self.shooter_path
        )
        quality = audit["shooter_observation_quality"]
        self.assertEqual(quality["shooters_loaded"], 2)
        self.assertIs(quality["colour_independently_verified"], False)
        self.assertIs(quality["ammunition_independently_verified"], False)
        self.assertIs(quality["slot_mapping_independently_verified"], False)
        self.assertEqual(quality["sample_quality_counts"], {
            "NOT_RECORDED": 2
        })
        self.assertEqual(
            quality["ammunition_ocr_status_counts"],
            {"PARSED_EXACT_DIGITS": 2},
        )
        self.assertIs(state.shooters["top_1"].observation_quality[
            "ammunition_independently_verified"
        ], False)
        self.assertEqual(
            state.shooters["top_1"].observation_quality[
                "ammunition_ocr_status"
            ],
            "PARSED_EXACT_DIGITS",
        )

    def test_matching_verified_shooter_capture_provenance_passes(self):
        self.shooters["capture_provenance"] = {
            "verified": True,
            "source_sha256": "a" * 64,
            "capture_session_id": "session-test-1",
            "captured_at": "2026-11-23T12:30:00+03:00",
        }
        self.write()
        _, audit = load_observed_level(
            self.observation_path, self.shooter_path
        )
        self.assertTrue(audit["shooter_capture_provenance_verified"])
        self.assertTrue(audit["shooter_capture_source_matches_board"])

    def test_matching_hash_with_wrong_session_or_timestamp_stays_unverified(self):
        cases = (
            {
                "verified": True,
                "source_sha256": "a" * 64,
                "capture_session_id": "different-session",
                "captured_at": "2026-11-23T12:30:00+03:00",
            },
            {
                "verified": True,
                "source_sha256": "a" * 64,
                "capture_session_id": "session-test-1",
                "captured_at": "2026-11-23T12:31:00+03:00",
            },
        )
        for provenance in cases:
            with self.subTest(provenance=provenance):
                self.shooters["capture_provenance"] = provenance
                self.write()
                state, audit = load_observed_level(
                    self.observation_path, self.shooter_path
                )
                self.assertFalse(
                    audit["shooter_capture_provenance_verified"]
                )
                self.assertEqual(
                    run_dry_simulation(state)["status"],
                    "BLOCKED_UNVERIFIED_CAPTURE_PROVENANCE",
                )
                schedule = run_multi_batch_schedule(state, [])
                self.assertFalse(schedule["schedule_valid"])
                self.assertEqual(
                    schedule["failure_reason"],
                    "UNVERIFIED_SHOOTER_CAPTURE_PROVENANCE",
                )

    def test_mismatched_shooter_capture_provenance_stays_unverified(self):
        self.shooters["capture_provenance"] = {
            "verified": True,
            "source_sha256": "b" * 64,
            "capture_session_id": "session-test-1",
            "captured_at": "2026-11-23T12:30:00+03:00",
        }
        self.write()
        _, audit = load_observed_level(
            self.observation_path, self.shooter_path
        )
        self.assertFalse(audit["shooter_capture_provenance_verified"])
        self.assertFalse(audit["shooter_capture_source_matches_board"])

    def test_unverified_capture_provenance_blocks_both_planners(self):
        state, audit = load_observed_level(
            self.observation_path, self.shooter_path
        )
        self.assertFalse(audit["shooter_capture_provenance_verified"])

        dry = run_dry_simulation(state)
        self.assertEqual(
            dry["status"], "BLOCKED_UNVERIFIED_CAPTURE_PROVENANCE"
        )
        self.assertEqual(dry["candidates_examined"], 0)
        self.assertFalse(dry["live_execution_allowed"])

        schedule = run_multi_batch_schedule(state, [])
        self.assertFalse(schedule["schedule_valid"])
        self.assertEqual(
            schedule["failure_reason"],
            "UNVERIFIED_SHOOTER_CAPTURE_PROVENANCE",
        )
        self.assertEqual(schedule["batches_completed"], 0)
        self.assertFalse(schedule["live_execution_allowed"])

    def test_verified_matching_capture_provenance_allows_dry_search_entry(self):
        self.shooters["capture_provenance"] = {
            "verified": True,
            "source_sha256": "a" * 64,
            "capture_session_id": "session-test-1",
            "captured_at": "2026-11-23T12:30:00+03:00",
        }
        self.write()
        state, audit = load_observed_level(
            self.observation_path, self.shooter_path
        )
        self.assertTrue(audit["shooter_capture_provenance_verified"])
        result = run_dry_simulation(state)
        self.assertNotEqual(
            result["status"], "BLOCKED_UNVERIFIED_CAPTURE_PROVENANCE"
        )

    def test_unified_level_loader_accepts_explicit_screenshot_mode(self):
        state, audit = load_level(
            level=39,
            observation_path=self.observation_path,
            shooter_path=self.shooter_path,
        )
        self.assertEqual(state.level, 39)
        self.assertEqual(state.width, 3)
        self.assertEqual(state.height, 2)
        self.assertEqual(audit["source"], "screenshot_observation")
        self.assertFalse(audit["game_taps_enabled"])

    def test_level_loader_cli_completes_screenshot_mode(self):
        output = StringIO()
        argv = [
            "level_loader.py",
            "--observation", str(self.observation_path),
            "--shooters", str(self.shooter_path),
        ]
        with patch.object(sys, "argv", argv), redirect_stdout(output):
            runpy.run_module("level_loader", run_name="__main__")
        self.assertIn("SCREENSHOT OBSERVATION INTEGRATION PASSED", output.getvalue())
        self.assertIn("Game taps enabled: False", output.getvalue())

    def test_rejects_board_dimensions_that_do_not_match_grid(self):
        self.observation["board"] = [["cyan"]]
        self.write()
        with self.assertRaisesRegex(ValueError, "Board row count"):
            load_observed_level(self.observation_path, self.shooter_path)

    def test_all_verification_and_action_flags_stay_false(self):
        _, audit = load_observed_level(
            self.observation_path, self.shooter_path
        )
        for key in (
            "shooter_positions_gameplay_verified",
            "shooter_capture_provenance_verified",
            "initial_occupancy_confirmed",
            "vision_classification_verified",
            "colour_mapping_verified",
            "board_transition_verified",
            "gameplay_verified",
            "game_taps_enabled",
        ):
            self.assertFalse(audit[key])
        self.assertTrue(audit["classification_consistent_with_extractor"])
        self.assertFalse(audit["colour_truth_verified"])

    def test_rejects_mismatched_colour_counts(self):
        self.observation["counts"]["cyan"] = 99
        self.write()
        with self.assertRaisesRegex(ValueError, "colour counts"):
            load_observed_level(self.observation_path, self.shooter_path)

    def test_rejects_rgb_and_saved_label_mismatch(self):
        self.observation["board"][0][0] = "red"
        self.write()
        with self.assertRaisesRegex(ValueError, "RGB/classification mismatch"):
            load_observed_level(self.observation_path, self.shooter_path)

    def test_rejects_invalid_rgb_sample(self):
        self.observation["raw_rgb"][0][0] = [256, 0, 0]
        self.write()
        with self.assertRaisesRegex(ValueError, "RGB sample"):
            load_observed_level(self.observation_path, self.shooter_path)

    def test_rejects_snapshot_identity_mismatch(self):
        self.observation["snapshot_id"] = "sha256:" + "b" * 64
        self.write()
        with self.assertRaisesRegex(ValueError, "board snapshot identity"):
            load_observed_level(self.observation_path, self.shooter_path)

    def test_rejects_missing_board_snapshot_binding(self):
        self.observation.pop("board_snapshot_id")
        self.write()
        with self.assertRaisesRegex(ValueError, "snapshot identity"):
            load_observed_level(self.observation_path, self.shooter_path)

    def test_rejects_attempt_to_mark_visuals_verified(self):
        self.observation["vision_classification_verified"] = True
        self.write()
        with self.assertRaisesRegex(ValueError, "colours must remain unverified"):
            load_observed_level(self.observation_path, self.shooter_path)

    def test_rejects_attempt_to_enable_game_taps(self):
        self.observation["game_taps_enabled"] = True
        self.write()
        with self.assertRaisesRegex(ValueError, "actions must remain disabled"):
            load_observed_level(self.observation_path, self.shooter_path)

    def test_rejects_non_object_shooter_detection_root(self):
        for malformed in ([], None, "invalid"):
            with self.subTest(malformed=malformed):
                self.shooter_path.write_text(json.dumps(malformed))
                with self.assertRaisesRegex(
                    ValueError, "Shooter detection must be a JSON object"
                ):
                    load_observed_level(
                        self.observation_path, self.shooter_path
                    )



    def test_rejects_sample_centres_that_disagree_with_calibration(self):
        self.observation["sample_centres"] = {
            "x": [11, 150, 289], "y": [20, 100]
        }
        self.write()
        with self.assertRaisesRegex(ValueError, "Sample centres do not match"):
            load_observed_level(self.observation_path, self.shooter_path)

    def test_accepts_matching_sample_centres(self):
        self.observation["sample_centres"] = {
            "x": [57, 150, 243], "y": [55, 145]
        }
        self.write()
        _, audit = load_observed_level(self.observation_path, self.shooter_path)
        self.assertEqual(audit["grid_size"], [3, 2])

    def test_independently_recomputes_all_source_rgb_samples(self):
        from PIL import Image
        import hashlib
        from io import BytesIO

        image = Image.new("RGB", (30, 30), (0, 0, 0))
        centres = {"x": [7, 15, 23], "y": [9, 21]}
        colours = [
            [(230, 30, 30), (10, 180, 230), (245, 245, 245)],
            [(200, 120, 60), (240, 80, 220), (20, 180, 70)],
        ]
        for row, y in enumerate(centres["y"]):
            for col, x in enumerate(centres["x"]):
                for py in range(y - 1, y + 2):
                    for px in range(x - 1, x + 2):
                        image.putpixel((px, py), colours[row][col])
        stream = BytesIO()
        image.save(stream, format="PNG")
        image_bytes = stream.getvalue()
        observation = {
            "source_sha256": hashlib.sha256(image_bytes).hexdigest(),
            "image_size": [30, 30],
            "grid_size": [3, 2],
            "bounds": [3, 3, 27, 27],
            "sample_centres": centres,
            "raw_rgb": [[list(c) for c in row] for row in colours],
        }
        result = verify_source_samples(observation, image_bytes)
        self.assertEqual(result["source_rgb_samples_recomputed"], 6)
        self.assertTrue(result["source_rgb_samples_match"])

    def test_rejects_source_rgb_sample_that_differs_from_image(self):
        from PIL import Image
        import hashlib
        from io import BytesIO

        image = Image.new("RGB", (30, 30), (245, 245, 245))
        stream = BytesIO()
        image.save(stream, format="PNG")
        image_bytes = stream.getvalue()
        observation = {
            "source_sha256": hashlib.sha256(image_bytes).hexdigest(),
            "image_size": [30, 30],
            "grid_size": [1, 1],
            "bounds": [3, 3, 27, 27],
            "sample_centres": {"x": [15], "y": [15]},
            "raw_rgb": [[[230, 30, 30]]],
        }
        with self.assertRaisesRegex(ValueError, "Source RGB sample mismatch"):
            verify_source_samples(observation, image_bytes)

    def test_rejects_source_image_hash_mismatch_before_sampling(self):
        from PIL import Image
        from io import BytesIO

        stream = BytesIO()
        Image.new("RGB", (30, 30), (245, 245, 245)).save(stream, format="PNG")
        observation = {"source_sha256": "0" * 64}
        with self.assertRaisesRegex(ValueError, "SHA-256 does not match"):
            verify_source_samples(observation, stream.getvalue())

    def test_matching_but_malformed_capture_timestamps_stay_unverified(self):
        self.observation["captured_at"] = "not-a-timestamp"
        self.shooters["capture_provenance"] = {
            "verified": True,
            "source_sha256": "a" * 64,
            "capture_session_id": "session-test-1",
            "captured_at": "not-a-timestamp",
        }
        self.write()
        _, audit = load_observed_level(
            self.observation_path, self.shooter_path
        )
        self.assertFalse(audit["board_capture_metadata_valid"])
        self.assertFalse(audit["shooter_capture_metadata_valid"])
        self.assertFalse(audit["shooter_capture_provenance_verified"])

    def test_matching_but_malformed_session_ids_stay_unverified(self):
        self.observation["capture_session_id"] = "invalid session id"
        self.shooters["capture_provenance"] = {
            "verified": True,
            "source_sha256": "a" * 64,
            "capture_session_id": "invalid session id",
            "captured_at": "2026-11-23T12:30:00+03:00",
        }
        self.write()
        _, audit = load_observed_level(
            self.observation_path, self.shooter_path
        )
        self.assertFalse(audit["board_capture_metadata_valid"])
        self.assertFalse(audit["shooter_capture_metadata_valid"])
        self.assertFalse(audit["shooter_capture_provenance_verified"])

    def test_rejects_non_finite_and_extreme_board_bounds_without_overflow(self):
        for invalid_bound in (float("nan"), float("inf"), float("-inf"), 10**1000, True):
            with self.subTest(bound_type=type(invalid_bound).__name__):
                self.observation["bounds"] = [
                    10, 10, invalid_bound, 190
                ]
                self.write()
                with self.assertRaises(ValueError):
                    load_observed_level(
                        self.observation_path, self.shooter_path
                    )
        self.observation["bounds"] = [10, 10, 290, 190]
        self.write()


if __name__ == "__main__":
    unittest.main(verbosity=2)
