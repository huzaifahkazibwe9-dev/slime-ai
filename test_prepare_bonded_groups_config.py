import json
import tempfile
import unittest
from pathlib import Path

from prepare_bonded_groups_config import prepare_config


class PrepareBondedGroupsConfigTests(unittest.TestCase):
    def test_creates_blank_unverified_config_without_inference(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "data" / "bonded_groups_confirmed.json"
            result = prepare_config(output)
            data = json.loads(output.read_text(encoding="utf-8"))

        self.assertTrue(result["created"])
        self.assertFalse(result["preserved_existing"])
        self.assertFalse(data["verified_by_user"])
        self.assertEqual(data["bonded_groups"], [])
        self.assertTrue(data["template_only"])
        self.assertFalse(data.get("gameplay_verified", False))

    def test_existing_user_bond_config_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "bonded_groups_confirmed.json"
            existing = {
                "verified_by_user": True,
                "bonded_groups": [["top_1", "top_2"]],
                "user_note": "confirmed manually",
            }
            output.write_text(json.dumps(existing), encoding="utf-8")
            before = output.read_bytes()

            result = prepare_config(output)

            self.assertFalse(result["created"])
            self.assertTrue(result["preserved_existing"])
            self.assertEqual(output.read_bytes(), before)

    def test_malformed_existing_config_is_preserved_for_review(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "bonded_groups_confirmed.json"
            original = b"{ invalid JSON"
            output.write_bytes(original)

            result = prepare_config(output)

            self.assertTrue(result["preserved_existing"])
            self.assertEqual(output.read_bytes(), original)


if __name__ == "__main__":
    unittest.main(verbosity=2)
