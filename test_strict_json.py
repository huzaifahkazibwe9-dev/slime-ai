import unittest

from strict_json import strict_json_loads


class StrictJsonTests(unittest.TestCase):
    def test_accepts_utf8_bytes_and_nested_objects(self):
        self.assertEqual(
            strict_json_loads(b'{"outer":{"value":3},"items":[1,true,null]}'),
            {"outer": {"value": 3}, "items": [1, True, None]},
        )

    def test_rejects_duplicate_top_level_object_keys(self):
        with self.assertRaisesRegex(ValueError, "Duplicate JSON object key: 'state'"):
            strict_json_loads('{"state":"safe","state":"unsafe"}')

    def test_rejects_duplicate_nested_object_keys(self):
        with self.assertRaisesRegex(ValueError, "Duplicate JSON object key: 'enabled'"):
            strict_json_loads('{"outer":{"enabled":false,"enabled":true}}')

    def test_rejects_non_standard_numeric_constants(self):
        for token in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(token=token):
                with self.assertRaisesRegex(ValueError, "Non-standard JSON numeric constant"):
                    strict_json_loads('{"reading":' + token + '}')

    def test_accepts_finite_float_exponents(self):
        self.assertEqual(
            strict_json_loads('{"reading":1.25e3,"max":1.7976931348623157e308}'),
            {"reading": 1250.0, "max": 1.7976931348623157e308},
        )

    def test_rejects_exponents_that_overflow_to_infinity(self):
        for token in ("1e999", "-1e999"):
            with self.subTest(token=token):
                with self.assertRaisesRegex(ValueError, "outside the finite range"):
                    strict_json_loads('{"reading":' + token + '}')

    def test_rejects_invalid_utf8_bytes(self):
        with self.assertRaises(UnicodeDecodeError):
            strict_json_loads(b'{"value":"' + bytes((255,)) + b'"}')


if __name__ == "__main__":
    unittest.main()
