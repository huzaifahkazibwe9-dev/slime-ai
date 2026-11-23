import unittest

from capture_provenance import (
    parse_exif_capture_time,
    validate_capture_session_id,
)


class CaptureProvenanceTests(unittest.TestCase):
    def test_exif_time_with_offset_becomes_aware_iso_timestamp(self):
        result = parse_exif_capture_time({
            36867: "2026:11:23 12:30:00",
            36881: "+03:00",
        })
        self.assertEqual(result, "2026-11-23T12:30:00+03:00")

    def test_exif_time_without_offset_is_not_claimed_as_absolute(self):
        self.assertIsNone(parse_exif_capture_time({
            36867: "2026:11:23 12:30:00",
        }))

    def test_invalid_exif_offset_is_rejected(self):
        self.assertIsNone(parse_exif_capture_time({
            36867: "2026:11:23 12:30:00",
            36881: "+18:00",
        }))

    def test_explicit_capture_timestamp_with_offset_is_accepted(self):
        from capture_provenance import parse_aware_capture_timestamp
        self.assertEqual(
            parse_aware_capture_timestamp("2026-11-23T12:30:00+03:00"),
            "2026-11-23T12:30:00+03:00",
        )

    def test_explicit_capture_timestamp_without_offset_is_rejected(self):
        from capture_provenance import parse_aware_capture_timestamp
        with self.assertRaisesRegex(ValueError, "UTC offset"):
            parse_aware_capture_timestamp("2026-11-23T12:30:00")

    def test_invalid_explicit_capture_timestamp_is_rejected(self):
        from capture_provenance import parse_aware_capture_timestamp
        with self.assertRaisesRegex(ValueError, "Invalid capture timestamp"):
            parse_aware_capture_timestamp("yesterday")

    def test_explicit_capture_session_id_is_preserved(self):
        self.assertEqual(
            validate_capture_session_id("session-2026-11-23-A"),
            "session-2026-11-23-A",
        )

    def test_malformed_capture_session_id_is_rejected(self):
        with self.assertRaises(ValueError):
            validate_capture_session_id("invalid session id")

    def test_missing_capture_session_is_not_invented(self):
        self.assertIsNone(validate_capture_session_id(None))


if __name__ == "__main__":
    unittest.main()
