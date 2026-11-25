import json
import tempfile
import unittest
from pathlib import Path

from prepare_shooter_review_pair import prepare_review_pair
from test_prepare_shooter_labels import fixture_artifacts


class PrepareShooterReviewPairTests(unittest.TestCase):
    def _sources(self, root):
        _, detection_bytes, screenshot_bytes = fixture_artifacts()
        detection = root / "detection.json"
        screenshot = root / "screenshot.png"
        detection.write_bytes(detection_bytes)
        screenshot.write_bytes(screenshot_bytes)
        return detection, screenshot, detection_bytes, screenshot_bytes

    def test_creates_two_separate_blank_source_bound_templates_and_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            detection, screenshot, _, _ = self._sources(root)
            result = prepare_review_pair(
                detection,
                screenshot,
                root / "review-pair",
                "reviewer-a",
                "reviewer-b",
            )

            dataset_a = json.loads(result["reviewer_a_dataset"].read_text())
            dataset_b = json.loads(result["reviewer_b_dataset"].read_text())
            manifest = json.loads(result["manifest"].read_text())

        self.assertEqual(len(dataset_a["samples"]), 12)
        self.assertEqual(len(dataset_b["samples"]), 12)
        self.assertFalse(dataset_a["labelled_by_user"])
        self.assertFalse(dataset_b["labelled_by_user"])
        self.assertEqual(
            dataset_a["source_detection_sha256"],
            dataset_b["source_detection_sha256"],
        )
        self.assertEqual(
            dataset_a["source_screenshot_sha256"],
            dataset_b["source_screenshot_sha256"],
        )
        self.assertIsNot(dataset_a, dataset_b)
        for sample_a, sample_b in zip(
            dataset_a["samples"], dataset_b["samples"]
        ):
            self.assertEqual(sample_a["review_status"], "not_reviewed")
            self.assertEqual(sample_b["review_status"], "not_reviewed")
            self.assertEqual(sample_a["human"], sample_b["human"])
            self.assertEqual(sample_a["human"]["visibility"], "")
            self.assertEqual(sample_b["human"]["visibility"], "")
        self.assertEqual(manifest["schema_version"], 1)
        self.assertEqual(len(manifest["captures"]), 1)
        entry = manifest["captures"][0]
        self.assertEqual(entry["reviewer_a_dataset"], "reviewer-a.json")
        self.assertEqual(entry["reviewer_b_dataset"], "reviewer-b.json")
        self.assertEqual(entry["detection"], "../detection.json")
        self.assertEqual(entry["screenshot"], "../screenshot.png")

    def test_refuses_to_overwrite_existing_templates_by_default(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            detection, screenshot, _, _ = self._sources(root)
            output = root / "pair"
            prepare_review_pair(detection, screenshot, output)
            with self.assertRaisesRegex(FileExistsError, "Refusing to overwrite"):
                prepare_review_pair(detection, screenshot, output)
            self.assertTrue((output / "reviewer-a.json").exists())
            self.assertTrue((output / "reviewer-b.json").exists())

    def test_explicit_overwrite_replaces_existing_pair(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            detection, screenshot, _, _ = self._sources(root)
            output = root / "pair"
            prepare_review_pair(detection, screenshot, output)
            reviewer_a = output / "reviewer-a.json"
            reviewer_a.write_text('{"edited": true}', encoding="utf-8")
            prepare_review_pair(
                detection, screenshot, output, overwrite=True
            )
            self.assertFalse(json.loads(reviewer_a.read_text()).get("edited"))

    def test_rejects_duplicate_or_unsafe_reviewer_ids(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            detection, screenshot, _, _ = self._sources(root)
            with self.assertRaisesRegex(ValueError, "must be distinct"):
                prepare_review_pair(
                    detection, screenshot, root / "pair",
                    "Reviewer-A", "reviewer-a",
                )
            with self.assertRaisesRegex(ValueError, "1-40 letters"):
                prepare_review_pair(
                    detection, screenshot, root / "pair",
                    "../outside", "reviewer-b",
                )

    def test_refuses_output_paths_that_collide_with_source_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            detection, screenshot, _, _ = self._sources(root)
            with self.assertRaisesRegex(ValueError, "must not overwrite source artifacts"):
                prepare_review_pair(
                    detection,
                    screenshot,
                    root,
                    "detection",
                    "reviewer-b",
                    overwrite=True,
                )

    def test_rejects_screenshot_not_bound_to_detector(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            detection, screenshot, _, _ = self._sources(root)
            screenshot.write_bytes(screenshot.read_bytes() + b"x")
            with self.assertRaisesRegex(ValueError, "SHA-256 does not match"):
                prepare_review_pair(
                    detection, screenshot, root / "pair"
                )


if __name__ == "__main__":
    unittest.main(verbosity=2)
