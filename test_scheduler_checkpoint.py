import json
import unittest

from conveyor_simulator import create_simulator, SimulatorConfig
from scheduler_checkpoint import (
    create_scheduler_checkpoint,
    restore_scheduler_checkpoint,
)


class SchedulerCheckpointTests(unittest.TestCase):
    def make_simulator(self):
        return create_simulator(
            [{"id": "A", "group_id": "A", "ammo": 2}],
            config=SimulatorConfig(conveyor_capacity=2, storage_capacity=3),
        )

    def test_json_round_trip_preserves_scheduler_and_simulator_state(self):
        sim = self.make_simulator()
        sim.select_group("A")
        sim.record_shots("A", 1)
        sim.tick(1)
        reports = [{"batch": 0, "valid": True, "groups": ["A"]}]
        checkpoint = create_scheduler_checkpoint(
            sim, 1, reports, ["A"]
        )

        encoded = json.dumps(checkpoint, allow_nan=False)
        restored = restore_scheduler_checkpoint(json.loads(encoded))

        self.assertEqual(restored["next_batch_index"], 1)
        self.assertEqual(restored["completed_batch_reports"], reports)
        self.assertEqual(restored["groups_scheduled"], ["A"])
        self.assertEqual(restored["simulator"].tick_count, sim.tick_count)
        self.assertEqual(
            restored["simulator"].shooters[0].ammo,
            sim.shooters[0].ammo,
        )
        self.assertFalse(restored["live_execution_allowed"])
        self.assertFalse(restored["gameplay_actions_performed"])

    def test_checkpoint_rejects_failed_or_incomplete_report(self):
        with self.assertRaisesRegex(ValueError, "successfully completed"):
            create_scheduler_checkpoint(
                self.make_simulator(), 1,
                [{"batch": 0, "valid": False}], [],
            )

    def test_checkpoint_requires_index_to_match_report_count(self):
        with self.assertRaisesRegex(ValueError, "report count"):
            create_scheduler_checkpoint(
                self.make_simulator(), 2,
                [{"batch": 0, "valid": True}], ["A"],
            )

    def test_restore_rejects_duplicate_scheduled_groups(self):
        checkpoint = create_scheduler_checkpoint(
            self.make_simulator(), 0, [], [],
        )
        checkpoint["groups_scheduled"] = ["A", "A"]
        with self.assertRaisesRegex(ValueError, "duplicates"):
            restore_scheduler_checkpoint(checkpoint)

    def test_restore_rejects_live_execution_flag(self):
        checkpoint = create_scheduler_checkpoint(
            self.make_simulator(), 0, [], [],
        )
        checkpoint["live_execution_allowed"] = True
        with self.assertRaisesRegex(ValueError, "cannot enable"):
            restore_scheduler_checkpoint(checkpoint)


if __name__ == "__main__":
    unittest.main(verbosity=2)
