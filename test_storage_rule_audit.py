import unittest

from storage_rule_audit import audit_storage_rules


class Build11WTests(unittest.TestCase):
    def test_audit_runs(self):
        report = audit_storage_rules()
        self.assertEqual(
            report["audit"], "Build11W_storage_rule_audit"
        )

    def test_gameplay_rule_remains_unverified(self):
        report = audit_storage_rules()
        self.assertFalse(report["gameplay_rule_verified"])

    def test_live_execution_remains_disabled(self):
        report = audit_storage_rules()
        self.assertFalse(report["live_execution_enabled"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
