import unittest
from multi_batch_planner import simulate_batch_schedule
from conveyor_simulator import SimulatorConfig


class MultiBatchTests(unittest.TestCase):
    def test_next_batch_after_return(self):
        records = [
            {"id": "A", "group_id": "A", "ammo": 1},
            {"id": "B", "group_id": "B", "ammo": 1},
        ]
        r = simulate_batch_schedule(records, [
            {"groups": ["A"], "shots": {"A": 1}},
            {"groups": ["B"], "shots": {"B": 1}},
        ], config=SimulatorConfig(conveyor_capacity=1, ticks_per_lap=4))
        self.assertTrue(r["schedule_valid"])
        self.assertEqual(r["batches_completed"], 2)
        self.assertEqual(r["returned_shooters"], ["A", "B"])
        self.assertEqual(r["storage_occupied"], 2)

    def test_active_shooter_blocks_next_batch(self):
        records = [
            {"id": "A", "group_id": "A", "ammo": 8},
            {"id": "B", "group_id": "B", "ammo": 1},
        ]
        r = simulate_batch_schedule(records, [
            {"groups": ["A"], "shots": {"A": 1}},
            {"groups": ["B"], "shots": {"B": 1}},
        ], config=SimulatorConfig(conveyor_capacity=1, ticks_per_lap=4))
        self.assertFalse(r["schedule_valid"])
        self.assertEqual(r["batches_completed"], 1)
        self.assertEqual(r["batch_reports"][-1]["reason"],
                         "INSUFFICIENT_CONVEYOR_SPACE")

    def test_bonded_group_selected_together(self):
        records = [
            {"id": "A1", "group_id": "PAIR", "ammo": 1},
            {"id": "A2", "group_id": "PAIR", "ammo": 1},
        ]
        r = simulate_batch_schedule(records, [
            {"groups": ["PAIR"], "shots": {"A1": 1, "A2": 1}},
        ], config=SimulatorConfig(conveyor_capacity=2, ticks_per_lap=3))
        self.assertTrue(r["schedule_valid"])
        self.assertEqual(set(r["returned_shooters"]), {"A1", "A2"})

    def test_duplicate_group_rejected(self):
        r = simulate_batch_schedule(
            [{"id": "A", "group_id": "A", "ammo": 1}],
            [
                {"groups": ["A"], "shots": {"A": 1}},
                {"groups": ["A"], "shots": {"A": 0}},
            ],
        )
        self.assertFalse(r["schedule_valid"])
        self.assertEqual(r["batch_reports"][-1]["reason"],
                         "GROUP_SCHEDULED_MORE_THAN_ONCE")

    def test_full_storage_failure(self):
        r = simulate_batch_schedule(
            [{"id": "A", "group_id": "A", "ammo": 1}],
            [{"groups": ["A"], "shots": {"A": 1}}],
            storage_occupied=5,
            config=SimulatorConfig(storage_capacity=5, ticks_per_lap=2),
        )
        self.assertFalse(r["schedule_valid"])
        self.assertTrue(r["failed"])

    def test_live_actions_disabled(self):
        r = simulate_batch_schedule(
            [{"id": "A", "group_id": "A", "ammo": 2}],
            [{"groups": ["A"], "shots": {"A": 1}}],
        )
        self.assertFalse(r["live_execution_allowed"])
        self.assertFalse(r["gameplay_actions_performed"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
