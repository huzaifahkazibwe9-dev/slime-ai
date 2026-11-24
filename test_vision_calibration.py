import unittest

from vision_calibration import evaluate_dataset, validate_dataset


class VisionCalibrationTests(unittest.TestCase):
    def setUp(self):
        self.dataset = {
            "schema_version": 1,
            "labelled_by_user": True,
            "samples": [
                {"id": "cyan-1", "rgb": [104, 195, 233], "label": "cyan"},
                {"id": "red-1", "rgb": [230, 30, 30], "label": "red"},
                {"id": "red-labelled-orange", "rgb": [230, 30, 30], "label": "orange"},
                {"id": "white-1", "rgb": [245, 245, 245], "label": "white"},
            ],
        }

    def test_reports_accuracy_confusion_and_per_class_metrics(self):
        report = evaluate_dataset(self.dataset)
        self.assertEqual(report["sample_count"], 4)
        self.assertEqual(report["correct_count"], 3)
        self.assertEqual(report["accuracy"], 0.75)
        self.assertEqual(report["confusion_matrix"]["orange"]["red"], 1)
        self.assertEqual(report["per_class"]["red"]["precision"], 0.5)
        self.assertEqual(report["per_class"]["red"]["recall"], 1.0)
        self.assertEqual(report["per_class"]["orange"]["recall"], 0.0)

    def test_does_not_claim_independent_truth_or_gameplay_verification(self):
        report = evaluate_dataset(self.dataset)
        self.assertFalse(report["label_truth_independently_verified"])
        self.assertFalse(report["gameplay_verified"])
        self.assertFalse(report["game_taps_enabled"])
        self.assertIn("do not independently verify", report["interpretation"])

    def test_validates_user_labelled_dataset_gate(self):
        self.dataset["labelled_by_user"] = False
        with self.assertRaisesRegex(ValueError, "labelled_by_user"):
            validate_dataset(self.dataset)

    def test_rejects_duplicate_sample_ids(self):
        self.dataset["samples"].append(dict(self.dataset["samples"][0]))
        with self.assertRaisesRegex(ValueError, "Duplicate sample id"):
            validate_dataset(self.dataset)

    def test_rejects_boolean_and_out_of_range_rgb_channels(self):
        for rgb in ([True, 0, 0], [-1, 0, 0], [256, 0, 0], [0, 0]):
            with self.subTest(rgb=rgb):
                malformed = {
                    **self.dataset,
                    "samples": [{"id": "bad", "rgb": rgb, "label": "red"}],
                }
                with self.assertRaisesRegex(ValueError, "rgb must be"):
                    validate_dataset(malformed)

    def test_rejects_noncanonical_colour_label(self):
        for label in ("grey", "turquoise", " Red ", ""):
            with self.subTest(label=label):
                malformed = {
                    **self.dataset,
                    "samples": [{"id": "bad-label", "rgb": [10, 20, 30], "label": label}],
                }
                with self.assertRaisesRegex(ValueError, "label must be one of"):
                    validate_dataset(malformed)

    def test_accepts_every_canonical_classifier_label(self):
        from screenshot_ingestor import COLOUR_LABELS

        samples = [
            {"id": f"label-{index}", "rgb": [20, 30, 40], "label": label}
            for index, label in enumerate(COLOUR_LABELS)
        ]
        validated = validate_dataset({
            "schema_version": 1,
            "labelled_by_user": True,
            "samples": samples,
        })
        self.assertEqual([sample["label"] for sample in validated], list(COLOUR_LABELS))

    def test_rejects_empty_or_malformed_datasets(self):
        for malformed in (None, [], {}, {
            "schema_version": 1, "labelled_by_user": True, "samples": []
        }):
            with self.subTest(malformed=malformed):
                with self.assertRaises(ValueError):
                    validate_dataset(malformed)


if __name__ == "__main__":
    unittest.main(verbosity=2)
