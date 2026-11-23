import json
import tempfile
import unittest
from pathlib import Path

from shooter_loader import load_shooters


class ShooterLoaderStructureTests(unittest.TestCase):
    def load_payload(self, payload):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "shooters.json"
            path.write_text(json.dumps(payload))
            return load_shooters(path)

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

    def test_rejects_invalid_colour_record(self):
        for value in (None, {}, {"name": ""}, {"name": 4}):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "invalid colour"):
                    self.load_payload({
                        "visible_shooters": [{"id": "shooter-1", "color": value}]
                    })


if __name__ == "__main__":
    unittest.main(verbosity=2)
