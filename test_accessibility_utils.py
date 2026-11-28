import unittest
from accessibility_utils import normalize_accessible_ids


class AccessibilityUtilsTests(unittest.TestCase):
    def test_none_returns_empty_set(self):
        self.assertEqual(normalize_accessible_ids(None), set())

    def test_empty_iterable_returns_empty_set(self):
        self.assertEqual(normalize_accessible_ids([]), set())
        self.assertEqual(normalize_accessible_ids(()), set())

    def test_list_of_ids_normalized(self):
        self.assertEqual(normalize_accessible_ids(["a", "b", 3]), {"a", "b", "3"})

    def test_string_rejected(self):
        with self.assertRaises(TypeError):
            normalize_accessible_ids("abc")

    def test_bytes_rejected(self):
        with self.assertRaises(TypeError):
            normalize_accessible_ids(b"abc")

    def test_dict_rejected(self):
        with self.assertRaises(TypeError):
            normalize_accessible_ids({"a": 1})

    def test_non_iterable_rejected(self):
        with self.assertRaises(TypeError):
            normalize_accessible_ids(42)

    def test_set_of_ids_accepted(self):
        self.assertEqual(normalize_accessible_ids({"x", "y"}), {"x", "y"})


if __name__ == "__main__":
    unittest.main()
