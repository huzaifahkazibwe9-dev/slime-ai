import json
import unittest
from pathlib import Path

DATA = Path("data")
REPORT = DATA / "conveyor_consistency_report.json"

@unittest.skipUnless(
    REPORT.is_file(),
    "Local conveyor consistency evidence is not included in the public repository"
)
class ConsistencyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = json.loads(REPORT.read_text())

    def test_overall_consistency(self):
        self.assertEqual(
            self.report["overall_status"],
            "CONSISTENT_POSITION_DATA"
        )

    def test_white_ammunition(self):
        self.assertEqual(
            self.report["position_series"]["white"]["ammunition"],
            [38, 33, 26, 26]
        )

    def test_blue_cyan_ammunition(self):
        self.assertEqual(
            self.report["position_series"]["blue_cyan"]["ammunition"],
            [40, 27, 18, 0]
        )

    def test_positions(self):
        self.assertEqual(
            self.report["position_series"]["white"]["positions"],
            ["bottom_1", "right_2", "top_2", "left_1"]
        )
        self.assertEqual(
            self.report["position_series"]["blue_cyan"]["positions"],
            ["bottom_2", "right_1", "top_1", "left_2"]
        )

    def test_safety_flags(self):
        self.assertFalse(self.report["identity_verified"])
        self.assertFalse(self.report["gameplay_verified"])
        self.assertFalse(self.report["game_taps_enabled"])
        for series in self.report["position_series"].values():
            self.assertNotIn("candidate_shooter", series)

if __name__ == "__main__":
    unittest.main(verbosity=2)
