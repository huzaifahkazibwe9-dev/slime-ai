import hashlib
import io
import unittest
from collections import Counter

from PIL import Image

from screenshot_ingestor import classify_rgb, sample_centres_for_grid
from source_pixel_audit import audit_source_pixels


class SourcePixelAuditTests(unittest.TestCase):
    def setUp(self):
        image = Image.new("RGB", (30, 30))
        for y in range(30):
            for x in range(30):
                image.putpixel((x, y), ((x * 7) % 256, (y * 9) % 256, ((x + y) * 5) % 256))
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        self.image_bytes = buffer.getvalue()
        centres = sample_centres_for_grid([3, 3], [3, 3, 27, 27])
        rgb_rows, board, counts = [], [], Counter()
        import statistics
        for y in centres["y"]:
            rgb_row, labels = [], []
            for x in centres["x"]:
                pixels = [
                    image.getpixel((px, py))
                    for py in range(y - 1, y + 2)
                    for px in range(x - 1, x + 2)
                ]
                rgb = [int(statistics.median(p[channel] for p in pixels)) for channel in range(3)]
                label = classify_rgb(rgb)
                rgb_row.append(rgb)
                labels.append(label)
                counts[label] += 1
            rgb_rows.append(rgb_row)
            board.append(labels)
        self.observation = {
            "source_sha256": hashlib.sha256(self.image_bytes).hexdigest(),
            "image_size": [30, 30],
            "grid_size": [3, 3],
            "bounds": [3, 3, 27, 27],
            "sample_centres": centres,
            "sampling_method": "numpy_vectorized_3x3_median",
            "raw_rgb": rgb_rows,
            "board": board,
            "counts": dict(counts),
        }

    def test_reproduces_all_source_pixel_samples(self):
        report = audit_source_pixels(self.observation, self.image_bytes)
        self.assertTrue(report["pixel_samples_reproduced"])
        self.assertEqual(report["reproduced_sample_count"], 9)
        self.assertTrue(report["colour_counts_match"])
        self.assertFalse(report["calibration_alignment_verified"])
        self.assertFalse(report["gameplay_verified"])
        self.assertFalse(report["game_taps_enabled"])

    def test_reports_corrupted_rgb_sample(self):
        self.observation["raw_rgb"][1][1][0] ^= 1
        report = audit_source_pixels(self.observation, self.image_bytes)
        self.assertFalse(report["pixel_samples_reproduced"])
        self.assertEqual(report["pixel_sample_mismatch_count"], 1)

    def test_rejects_source_hash_mismatch(self):
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            audit_source_pixels(self.observation, self.image_bytes + b"x")

    def test_rejects_source_dimension_mismatch(self):
        image = Image.new("RGB", (31, 30))
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        bad_bytes = buffer.getvalue()
        self.observation["source_sha256"] = hashlib.sha256(bad_bytes).hexdigest()
        with self.assertRaisesRegex(ValueError, "dimensions"):
            audit_source_pixels(self.observation, bad_bytes)

    def test_rejects_sample_centre_mismatch(self):
        self.observation["sample_centres"]["x"][0] += 1
        with self.assertRaisesRegex(ValueError, "sample_centres"):
            audit_source_pixels(self.observation, self.image_bytes)

    def test_rejects_malformed_grid_sample_shape(self):
        self.observation["raw_rgb"].pop()
        with self.assertRaisesRegex(ValueError, "row count"):
            audit_source_pixels(self.observation, self.image_bytes)

    def test_rejects_unsupported_sampling_method(self):
        self.observation["sampling_method"] = "unknown"
        with self.assertRaisesRegex(ValueError, "sampling_method"):
            audit_source_pixels(self.observation, self.image_bytes)

    def test_reports_colour_count_mismatch(self):
        self.observation["counts"] = {"white": 9}
        report = audit_source_pixels(self.observation, self.image_bytes)
        self.assertFalse(report["colour_counts_match"])

    def test_rejects_boolean_colour_count(self):
        self.observation["counts"] = {"white": True}
        report = audit_source_pixels(self.observation, self.image_bytes)
        self.assertFalse(report["colour_counts_match"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
