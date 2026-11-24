import unittest

from prepare_colour_labels import build_template


class ColourLabelTemplateTests(unittest.TestCase):
    def observation(self):
        return {
            "source_sha256": "a" * 64,
            "image_size": [1080, 2220],
            "grid_size": [2, 2],
            "raw_rgb": [
                [[10, 20, 30], [40, 50, 60]],
                [[70, 80, 90], [100, 110, 120]],
            ],
        }

    def test_builds_row_major_samples_without_guessing_labels(self):
        template = build_template(self.observation())
        self.assertEqual(len(template["samples"]), 4)
        self.assertEqual(template["samples"][0]["id"], "r01c01")
        self.assertEqual(template["samples"][2]["row"], 1)
        self.assertEqual(template["samples"][2]["column"], 0)
        self.assertEqual(template["samples"][2]["rgb"], [70, 80, 90])
        self.assertEqual([sample["label"] for sample in template["samples"]], [""] * 4)
        self.assertIs(template["labelled_by_user"], False)

    def test_preserves_valid_image_dimensions(self):
        template = build_template(self.observation())
        self.assertEqual(template["image_size"], [1080, 2220])

    def test_rejects_missing_or_malformed_image_dimensions(self):
        for image_size in (None, [], [1080], [1080, 0], [1080, True], "1080x2220"):
            with self.subTest(image_size=image_size):
                observation = self.observation()
                observation["image_size"] = image_size
                with self.assertRaises(ValueError):
                    build_template(observation)

    def test_output_metadata_and_rgb_are_detached_from_input(self):
        observation = self.observation()
        template = build_template(observation)

        observation["image_size"][0] = 1
        observation["grid_size"][0] = 1
        observation["raw_rgb"][0][0][0] = 255

        self.assertEqual(template["image_size"], [1080, 2220])
        self.assertEqual(template["grid_size"], [2, 2])
        self.assertEqual(template["samples"][0]["rgb"], [10, 20, 30])

    def test_rejects_missing_or_malformed_grid_dimensions(self):
        for grid_size in (None, [], [2], [0, 2], [2, True], "2x2"):
            with self.subTest(grid_size=grid_size):
                observation = self.observation()
                observation["grid_size"] = grid_size
                with self.assertRaises(ValueError):
                    build_template(observation)

    def test_rejects_malformed_rgb_rows(self):
        cases = (
            [],
            [[[1, 2, 3]]],
            [[ [1, 2, 3], [4, 5, 6] ], [ [7, 8, 9] ]],
        )
        for raw_rgb in cases:
            with self.subTest(raw_rgb=raw_rgb):
                observation = self.observation()
                observation["raw_rgb"] = raw_rgb
                with self.assertRaises(ValueError):
                    build_template(observation)

    def test_normalizes_uppercase_source_digest(self):
        observation = self.observation()
        observation["source_sha256"] = "A" * 64
        template = build_template(observation)
        self.assertEqual(template["source_sha256"], "a" * 64)

    def test_rejects_non_hex_source_digest(self):
        observation = self.observation()
        observation["source_sha256"] = "g" * 64
        with self.assertRaises(ValueError):
            build_template(observation)

    def test_rejects_non_object_observation(self):
        for observation in (None, [], "observation", 42):
            with self.subTest(observation=observation):
                with self.assertRaises(ValueError):
                    build_template(observation)

    def test_rejects_non_list_rgb_container_and_cells(self):
        for raw_rgb in (None, "rgb", {"rows": []}, [[None, [1, 2, 3]], [[4, 5, 6], [7, 8, 9]]]):
            with self.subTest(raw_rgb=raw_rgb):
                observation = self.observation()
                observation["raw_rgb"] = raw_rgb
                with self.assertRaises(ValueError):
                    build_template(observation)

    def test_rejects_non_integer_grid_values(self):
        for grid_size in ([2, 2.0], [2.5, 2], [True, 2]):
            with self.subTest(grid_size=grid_size):
                observation = self.observation()
                observation["grid_size"] = grid_size
                with self.assertRaises(ValueError):
                    build_template(observation)

    def test_rejects_grid_mismatch(self):
        observation = self.observation()
        observation["raw_rgb"] = [[[1, 2, 3]]]
        with self.assertRaises(ValueError):
            build_template(observation)

    def test_rejects_invalid_rgb_channel(self):
        observation = self.observation()
        observation["raw_rgb"][0][0] = [0, True, 255]
        with self.assertRaises(ValueError):
            build_template(observation)

    def test_rejects_missing_source_digest(self):
        observation = self.observation()
        observation["source_sha256"] = "not-a-digest"
        with self.assertRaises(ValueError):
            build_template(observation)


if __name__ == "__main__":
    unittest.main()
