import unittest
from unittest.mock import patch

import execution_engine
from test_execution_engine_build11r import make_state


class Build11ZIntegrityTests(unittest.TestCase):
    def test_normal_simulation_checks_full_source_state(self):
        state = make_state()
        result = execution_engine.run_multi_batch_schedule(state, [])

        self.assertTrue(result["source_state_integrity_checked"])
        self.assertTrue(result["source_state_unchanged"])

    def test_mutation_is_detected_and_schedule_rejected(self):
        state = make_state()

        def mutate_state(*args, **kwargs):
            state.storage.append("integrity_probe")
            return {"schedule_valid": True}

        with patch(
            "execution_engine._run_multi_batch_schedule_unchecked",
            side_effect=mutate_state
        ):
            result = execution_engine.run_multi_batch_schedule(state, [])

        self.assertTrue(result["source_state_integrity_checked"])
        self.assertFalse(result["source_state_unchanged"])
        self.assertFalse(result["schedule_valid"])
        self.assertEqual(
            result["failure_reason"],
            "SOURCE_STATE_MUTATED"
        )

    def test_live_execution_remains_disabled(self):
        state = make_state()
        result = execution_engine.run_multi_batch_schedule(state, [])

        self.assertFalse(result["live_execution_allowed"])
        self.assertFalse(result["gameplay_actions_performed"])


if __name__ == "__main__":
    unittest.main()
