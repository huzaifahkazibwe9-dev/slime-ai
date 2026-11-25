import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from prepare_identity_observations import (
    build_template,
    prepare_template,
    read_json_snapshot,
)


POSITIONS = [
    "bottom_1", "bottom_2", "right_1", "right_2",
    "top_1", "top_2", "left_1", "left_2",
]


def valid_inputs():
    board = {
        "source_sha256": "a" * 64,
        "snapshot_id": "sha256:" + "a" * 64,
        "board_snapshot_id": "sha256:" + "a" * 64,
        "capture_session_id": "session-001",
        "captured_at": "2026-11-25T10:00:00+00:00",
        "timestamp_identified": True,
    }
    calibration = {
        "shooters": [
            {
                "id": position,
                "segment": position.split("_")[0],
                "center": [index * 10 + 5, index * 10 + 7],
            }
            for index, position in enumerate(POSITIONS)
        ]
    }
    detection = {
        "visible_shooters": [
            {"id": f"shooter-{index}"}
            for index in range(4)
        ]
    }
    return board, calibration, detection


class PrepareIdentityObservationsTests(unittest.TestCase):
    def test_template_contains_only_unverified_current_and_history_records(self):
        board, calibration, detection = valid_inputs()
        template = build_template(
            board, calibration, detection,
            {
                "board_observation_json": "1" * 64,
                "conveyor_calibration_json": "2" * 64,
                "shooter_detection_json": "3" * 64,
            },
        )
        current = [
            item for item in template["observations"]
            if item["frame_id"] == template["current_frame_id"]
        ]
        historical = [
            item for item in template["observations"]
            if item["frame_id"] != template["current_frame_id"]
        ]
        self.assertEqual(len(current), 4)
        self.assertEqual(
            {item["shooter_id"] for item in current},
            {f"shooter-{index}" for index in range(4)},
        )
        self.assertEqual({item["position_id"] for item in historical}, set(POSITIONS))
        self.assertTrue(all(item["verified"] is False for item in template["observations"]))
        self.assertTrue(all(item["position_id"] == "" for item in current))
        self.assertTrue(all(item["shooter_id"] == "" for item in historical))
        self.assertFalse(template["verified_by_user"])
        self.assertFalse(template["gameplay_verified"])
        self.assertFalse(template["game_taps_enabled"])

    def test_template_rejects_missing_or_unidentified_board_timestamp(self):
        board, calibration, detection = valid_inputs()
        board["timestamp_identified"] = False
        with self.assertRaisesRegex(ValueError, "timestamp"):
            build_template(board, calibration, detection, {
                "board_observation_json": "1" * 64,
                "conveyor_calibration_json": "2" * 64,
                "shooter_detection_json": "3" * 64,
            })

    def test_template_rejects_invalid_calibration_slot_layout(self):
        board, calibration, detection = valid_inputs()
        calibration["shooters"].pop()
        with self.assertRaisesRegex(ValueError, "Missing calibrated position"):
            build_template(board, calibration, detection, {
                "board_observation_json": "1" * 64,
                "conveyor_calibration_json": "2" * 64,
                "shooter_detection_json": "3" * 64,
            })

    def test_template_rejects_duplicate_visible_shooter_ids(self):
        board, calibration, detection = valid_inputs()
        detection["visible_shooters"][1]["id"] = "shooter-0"
        with self.assertRaisesRegex(ValueError, "not unique"):
            build_template(board, calibration, detection, {
                "board_observation_json": "1" * 64,
                "conveyor_calibration_json": "2" * 64,
                "shooter_detection_json": "3" * 64,
            })

    def test_prepare_template_hashes_exact_input_bytes_and_writes_atomically(self):
        board, calibration, detection = valid_inputs()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = {}
            raw_bytes = {}
            for name, payload in (
                ("board.json", board),
                ("calibration.json", calibration),
                ("detection.json", detection),
            ):
                raw = json.dumps(payload, separators=(",", ":")).encode()
                raw_bytes[name] = raw
                paths[name] = root / name
                paths[name].write_bytes(raw)
            output = root / "data" / "shooter_identity_observations.json"

            result = prepare_template(
                paths["board.json"], paths["calibration.json"],
                paths["detection.json"], output,
            )
            saved = json.loads(output.read_text(encoding="utf-8"))

            self.assertTrue(result["created"])
            self.assertTrue(output.is_file())
            self.assertFalse(output.with_suffix(".json.tmp").exists())
            self.assertEqual(
                saved["source_file_sha256"],
                {
                    "board_observation_json": hashlib.sha256(raw_bytes["board.json"]).hexdigest(),
                    "conveyor_calibration_json": hashlib.sha256(raw_bytes["calibration.json"]).hexdigest(),
                    "shooter_detection_json": hashlib.sha256(raw_bytes["detection.json"]).hexdigest(),
                },
            )
            self.assertFalse(saved["verified_by_user"])

    def test_prepare_template_never_overwrites_existing_user_observations(self):
        board, calibration, detection = valid_inputs()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = []
            for name, payload in (
                ("board.json", board),
                ("calibration.json", calibration),
                ("detection.json", detection),
            ):
                path = root / name
                path.write_text(json.dumps(payload))
                paths.append(path)
            output = root / "shooter_identity_observations.json"
            existing = b'{"verified_by_user": true, "user_data": "keep"}'
            output.write_bytes(existing)

            result = prepare_template(*paths, output)

            self.assertFalse(result["created"])
            self.assertTrue(result["preserved_existing"])
            self.assertEqual(output.read_bytes(), existing)

    def test_read_json_snapshot_rejects_invalid_utf8(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            path.write_bytes(bytes((255, 254)))
            with self.assertRaisesRegex(ValueError, "invalid UTF-8 JSON"):
                read_json_snapshot(path)


if __name__ == "__main__":
    unittest.main(verbosity=2)
