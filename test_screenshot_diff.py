#!/usr/bin/env python3
"""Unit tests for pure offline screenshot difference helpers."""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image

import screenshot_diff


class BoardGeometryTests(unittest.TestCase):
    def test_reference_size_returns_reference_bounds(self):
        image = Image.new("RGB", screenshot_diff.REFERENCE_SIZE)
        bounds = screenshot_diff.board_geometry(image)
        self.assertEqual(bounds, screenshot_diff.REFERENCE_BOUNDS)

    def test_scales_bounds_with_image_size(self):
        image = Image.new("RGB", (2160, 4440))  # 2x reference
        bounds = screenshot_diff.board_geometry(image)
        expected = tuple(v * 2 for v in screenshot_diff.REFERENCE_BOUNDS)
        self.assertEqual(bounds, expected)


class ColourDifferenceTests(unittest.TestCase):
    def test_identical_colours_zero_difference(self):
        self.assertEqual(screenshot_diff.colour_difference((10, 20, 30), (10, 20, 30)), 0)

    def test_average_absolute_channel_difference(self):
        self.assertEqual(screenshot_diff.colour_difference((0, 0, 0), (30, 0, 0)), 10)
        self.assertEqual(screenshot_diff.colour_difference((0, 0, 0), (30, 30, 30)), 30)


class CellSampleTests(unittest.TestCase):
    def test_uniform_tile_returns_median_colour(self):
        image = Image.new("RGB", (100, 100), (50, 60, 70))
        bounds = (0, 0, 100, 100)
        # Force a single-cell grid for simplicity by temporarily adjusting constants
        original_cols, original_rows = screenshot_diff.COLS, screenshot_diff.ROWS
        try:
            screenshot_diff.COLS = 1
            screenshot_diff.ROWS = 1
            sample = screenshot_diff.cell_sample(image, bounds, 0, 0)
            self.assertEqual(sample, (50, 60, 70))
        finally:
            screenshot_diff.COLS = original_cols
            screenshot_diff.ROWS = original_rows

    def test_empty_crop_raises(self):
        image = Image.new("RGB", (10, 10))
        with self.assertRaises(ValueError):
            screenshot_diff.cell_sample(image, (0, 0, 1, 1), 0, 0)


class CompareTests(unittest.TestCase):
    def _solid(self, size, colour):
        return Image.new("RGB", size, colour)

    def test_identical_images_report_no_changes(self):
        with TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            before = tmp / "before.png"
            after = tmp / "after.png"
            img = self._solid((200, 200), (100, 100, 100))
            img.save(before)
            img.save(after)

            # Scale geometry so board fits
            original_ref = screenshot_diff.REFERENCE_SIZE
            original_bounds = screenshot_diff.REFERENCE_BOUNDS
            try:
                screenshot_diff.REFERENCE_SIZE = (200, 200)
                screenshot_diff.REFERENCE_BOUNDS = (10, 10, 190, 190)
                report = screenshot_diff.compare(before, after)
            finally:
                screenshot_diff.REFERENCE_SIZE = original_ref
                screenshot_diff.REFERENCE_BOUNDS = original_bounds

            self.assertEqual(report["changed_cell_count"], 0)
            self.assertFalse(report["actual_firing_verified"])
            self.assertFalse(report["gameplay_access_enabled"])
            self.assertEqual(report["interpretation"], "candidate_visual_changes_only")

    def test_size_mismatch_raises(self):
        with TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            before = tmp / "before.png"
            after = tmp / "after.png"
            self._solid((100, 100), (0, 0, 0)).save(before)
            self._solid((100, 101), (0, 0, 0)).save(after)
            with self.assertRaises(ValueError):
                screenshot_diff.compare(before, after)

    def test_detects_change_above_threshold(self):
        with TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            before = tmp / "before.png"
            after = tmp / "after.png"
            size = (200, 200)
            self._solid(size, (0, 0, 0)).save(before)
            changed = self._solid(size, (0, 0, 0))
            # Paint a region that will be sampled as different
            for x in range(30, 70):
                for y in range(30, 70):
                    changed.putpixel((x, y), (100, 0, 0))
            changed.save(after)

            original_ref = screenshot_diff.REFERENCE_SIZE
            original_bounds = screenshot_diff.REFERENCE_BOUNDS
            original_cols = screenshot_diff.COLS
            original_rows = screenshot_diff.ROWS
            try:
                screenshot_diff.REFERENCE_SIZE = size
                screenshot_diff.REFERENCE_BOUNDS = (0, 0, 200, 200)
                screenshot_diff.COLS = 2
                screenshot_diff.ROWS = 2
                report = screenshot_diff.compare(before, after)
            finally:
                screenshot_diff.REFERENCE_SIZE = original_ref
                screenshot_diff.REFERENCE_BOUNDS = original_bounds
                screenshot_diff.COLS = original_cols
                screenshot_diff.ROWS = original_rows

            self.assertGreater(report["changed_cell_count"], 0)
            self.assertFalse(report["actual_firing_verified"])


if __name__ == "__main__":
    unittest.main()
