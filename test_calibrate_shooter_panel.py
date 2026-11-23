import tempfile
import unittest
from pathlib import Path

from PIL import Image

from calibrate_shooter_panel import create_preview


class ShooterPanelCalibrationPreviewTests(unittest.TestCase):
    def test_preview_preserves_source_coordinate_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.png"
            output = Path(directory) / "preview.png"
            Image.new("RGB", (2000, 1000), "white").save(source)

            result = create_preview(source, output, step=100, max_width=1000)

            self.assertEqual(result["source_size"], [2000, 1000])
            self.assertEqual(result["preview_size"], [1000, 500])
            self.assertEqual(result["scale"], 0.5)
            self.assertTrue(output.is_file())
            with Image.open(output) as preview:
                self.assertEqual(preview.size, (1000, 500))

    def test_preview_rejects_invalid_grid_step(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.png"
            Image.new("RGB", (300, 200), "white").save(source)
            with self.assertRaises(ValueError):
                create_preview(source, Path(directory) / "out.png", step=0)

    def test_preview_rejects_too_small_width(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.png"
            Image.new("RGB", (300, 200), "white").save(source)
            with self.assertRaises(ValueError):
                create_preview(source, Path(directory) / "out.png",
                               max_width=100)


if __name__ == "__main__":
    unittest.main()
