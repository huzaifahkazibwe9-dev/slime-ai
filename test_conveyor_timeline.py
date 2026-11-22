import json
import unittest
from pathlib import Path

DATA = Path("data")
TIMELINE = DATA / "conveyor_timeline.json"
OBSERVATIONS = DATA / "conveyor_visual_observations.json"

@unittest.skipUnless(
    TIMELINE.is_file() and OBSERVATIONS.is_file(),
    "Local conveyor screenshots/observations are not included in the public repository"
)
class ConveyorTimelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.timeline = json.loads(TIMELINE.read_text())
        cls.original = json.loads(OBSERVATIONS.read_text())

    def test_four_stages(self):
        self.assertEqual(
            self.timeline["sequence"],
            ["bottom", "right", "top", "left"]
        )
        self.assertEqual(len(self.timeline["snapshots"]), 4)

    def test_white_ammunition(self):
        self.assertEqual(
            self.timeline["candidate_tracks"]["white"]["ammo"],
            [38, 33, 26, 26]
        )

    def test_blue_cyan_ammunition(self):
        self.assertEqual(
            self.timeline["candidate_tracks"]["blue_cyan"]["ammo"],
            [40, 27, 18, 0]
        )

    def test_all_eight_observations_preserved(self):
        original = {
            item["position_id"]: item
            for item in self.original["observations"]
        }
        for step in self.timeline["snapshots"]:
            for key in ("white_candidate", "blue_cyan_candidate"):
                item = step[key]
                self.assertEqual(
                    item,
                    original[item["position_id"]]
                )

    def test_safety_flags(self):
        self.assertFalse(self.timeline["identity_verified"])
        self.assertFalse(self.timeline["gameplay_taps_enabled"])
        self.assertFalse(self.timeline["timestamps_known"])

if __name__ == "__main__":
    unittest.main(verbosity=2)
