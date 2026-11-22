import unittest
from multi_batch_planner import simulate_batch_schedule
from conveyor_simulator import SimulatorConfig


class Build11TTests(unittest.TestCase):
    def test_reactivation_disabled_by_default(self):
        records = [{"id": "A", "group_id": "A", "ammo": 1}]
        batches = [
            {"groups": ["A"], "shots": {"A": 1}},
            {"groups": ["A"], "shots": {"A": 0},
             "reactivate_groups": ["A"]},
        ]
        r = simulate_batch_schedule(records, batches)
        self.assertFalse(r["schedule_valid"])
        self.assertEqual(
            r["batch_reports"][-1]["reason"],
            "STORAGE_REACTIVATION_NOT_ENABLED",
        )

    def test_single_group_can_reactivate_when_enabled(self):
        records = [{"id": "A", "group_id": "A", "ammo": 1}]
        batches = [
            {"groups": ["A"], "shots": {"A": 1}},
            {"groups": ["A"], "reactivate_groups": ["A"],
             "shots": {"A": 0}},
        ]
        r = simulate_batch_schedule(
            records, batches, allow_storage_reactivation=True
        )
        self.assertTrue(r["schedule_valid"])
        self.assertEqual(r["batches_completed"], 2)
        self.assertEqual(r["storage_occupied"], 1)
        self.assertEqual(r["returned_shooters"], ["A"])

    def test_bonded_group_reactivates_atomically(self):
        records = [
            {"id": "A1", "group_id": "PAIR", "ammo": 1},
            {"id": "A2", "group_id": "PAIR", "ammo": 1},
        ]
        batches = [
            {"groups": ["PAIR"], "shots": {"A1": 1, "A2": 1}},
            {"groups": ["PAIR"], "reactivate_groups": ["PAIR"],
             "shots": {"A1": 0, "A2": 0}},
        ]
        r = simulate_batch_schedule(
            records, batches,
            config=SimulatorConfig(conveyor_capacity=2),
            allow_storage_reactivation=True,
        )
        self.assertTrue(r["schedule_valid"])
        self.assertEqual(r["storage_occupied"], 2)
        self.assertEqual(set(r["returned_shooters"]), {"A1", "A2"})

    def test_bonded_group_cannot_reactivate_partially(self):
        records = [
            {"id": "A1", "group_id": "PAIR", "ammo": 1},
            {"id": "A2", "group_id": "PAIR", "ammo": 5},
        ]
        batches = [
            {"groups": ["PAIR"], "shots": {"A1": 1, "A2": 0}},
            {"groups": ["PAIR"], "reactivate_groups": ["PAIR"],
             "shots": {"A1": 0, "A2": 0}},
        ]
        r = simulate_batch_schedule(
            records, batches,
            config=SimulatorConfig(conveyor_capacity=2),
            allow_storage_reactivation=True,
        )
        self.assertFalse(r["schedule_valid"])
        self.assertEqual(
            r["batch_reports"][-1]["reason"],
            "GROUP_NOT_FULLY_RETURNED",
        )

    def test_reactivation_requires_group_capacity(self):
        records = [
            {"id": "A1", "group_id": "PAIR", "ammo": 1},
            {"id": "A2", "group_id": "PAIR", "ammo": 1},
            {"id": "B", "group_id": "B", "ammo": 5},
        ]
        batches = [
            {"groups": ["PAIR"], "shots": {"A1": 1, "A2": 1}},
            {"groups": ["B"], "shots": {"B": 0}},
            {"groups": ["PAIR"], "reactivate_groups": ["PAIR"],
             "shots": {"A1": 0, "A2": 0}},
        ]
        r = simulate_batch_schedule(
            records, batches,
            config=SimulatorConfig(conveyor_capacity=2),
            allow_storage_reactivation=True,
        )
        self.assertFalse(r["schedule_valid"])
        self.assertEqual(
            r["batch_reports"][-1]["reason"],
            "INSUFFICIENT_CONVEYOR_SPACE_FOR_REACTIVATION",
        )

    def test_live_actions_stay_disabled(self):
        r = simulate_batch_schedule(
            [{"id": "A", "group_id": "A", "ammo": 1}],
            [{"groups": ["A"], "shots": {"A": 1}}],
            allow_storage_reactivation=True,
        )
        self.assertFalse(r["live_execution_allowed"])
        self.assertFalse(r["gameplay_actions_performed"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
