import unittest
from pathlib import Path
from PIL import Image

from screenshot_ingestor import classify_rgb, extract_board


class ScreenshotIngestorTests(unittest.TestCase):
    def test_white_classification(self):
        self.assertEqual(classify_rgb((245, 245, 245)), "white")

    def test_cyan_classification(self):
        self.assertEqual(classify_rgb((104, 195, 233)), "cyan")

    def test_red_classification(self):
        self.assertEqual(classify_rgb((230, 30, 30)), "red")

    def test_extracts_complete_grid(self):
        path = Path("data/test_ingestor_image.png")
        path.parent.mkdir(exist_ok=True)
        Image.new("RGB", (30, 30), (245, 245, 245)).save(path)
        try:
            calibration = {
                "grid_size": [3, 3],
                "bounds": [3, 3, 27, 27],
            }
            result = extract_board(path, calibration)
            self.assertEqual(len(result["board"]), 3)
            self.assertTrue(all(len(row) == 3 for row in result["board"]))
            self.assertEqual(sum(result["counts"].values()), 9)
        finally:
            path.unlink(missing_ok=True)

    def test_rejects_image_too_small(self):
        path = Path("data/test_ingestor_small.png")
        path.parent.mkdir(exist_ok=True)
        Image.new("RGB", (10, 10)).save(path)
        try:
            with self.assertRaises(ValueError):
                extract_board(path, {
                    "grid_size": [3, 3],
                    "bounds": [3, 3, 27, 27],
                })
        finally:
            path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
