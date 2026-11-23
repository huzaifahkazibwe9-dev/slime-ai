import unittest

from conveyor_identity_matcher import validate_visual_observations


EXPECTED = [
    "bottom_1", "bottom_2", "right_1", "right_2",
    "top_1", "top_2", "left_1", "left_2",
]


def observations():
    return [
        {"position_id": position, "colour": "white", "ammo": 10}
        for position in EXPECTED
    ]


class ConveyorIdentityMatcherTests(unittest.TestCase):
    def test_complete_unique_frame_is_valid(self):
        self.assertEqual(
            validate_visual_observations(observations(), EXPECTED), []
        )

    def test_duplicate_position_rejected(self):
        data = observations()
        data[-1] = dict(data[0])
        errors = validate_visual_observations(data, EXPECTED)
        self.assertTrue(any("Duplicate position" in x for x in errors))

    def test_missing_position_rejected(self):
        errors = validate_visual_observations(
            observations()[:-1], EXPECTED
        )
        self.assertTrue(any("Missing positions" in x for x in errors))

    def test_unexpected_position_rejected(self):
        data = observations()
        data[-1]["position_id"] = "left_9"
        errors = validate_visual_observations(data, EXPECTED)
        self.assertTrue(any("Unexpected position" in x for x in errors))

    def test_negative_ammunition_rejected(self):
        data = observations()
        data[0]["ammo"] = -1
        errors = validate_visual_observations(data, EXPECTED)
        self.assertTrue(any("invalid ammunition" in x for x in errors))

    def test_boolean_ammunition_rejected(self):
        data = observations()
        data[0]["ammo"] = True
        errors = validate_visual_observations(data, EXPECTED)
        self.assertTrue(any("invalid ammunition" in x for x in errors))

    def test_unknown_colour_rejected(self):
        data = observations()
        data[0]["colour"] = "orange"
        errors = validate_visual_observations(data, EXPECTED)
        self.assertTrue(any("invalid colour" in x for x in errors))

    def test_non_list_rejected(self):
        self.assertTrue(
            validate_visual_observations(None, EXPECTED)
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
