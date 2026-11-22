import unittest

from conveyor_simulator import (
    ConveyorSimulator, Shooter, SimulatorConfig, create_simulator
)


class ConveyorSimulatorTests(unittest.TestCase):
    def test_bonded_group_selection_is_atomic(self):
        sim = create_simulator([
            {"id": "a", "group_id": "pair", "ammo": 10},
            {"id": "b", "group_id": "pair", "ammo": 10},
        ])
        self.assertTrue(sim.select_group("pair"))
        self.assertEqual(len(sim.active), 2)

    def test_group_rejected_when_capacity_is_insufficient(self):
        sim = create_simulator([
            {"id": "a", "group_id": "pair", "ammo": 10},
            {"id": "b", "group_id": "pair", "ammo": 10},
        ], config=SimulatorConfig(conveyor_capacity=1))
        self.assertFalse(sim.select_group("pair"))
        self.assertEqual(len(sim.active), 0)

    def test_completed_shooter_returns_after_one_lap(self):
        sim = create_simulator([
            {"id": "single", "group_id": "single", "ammo": 2}
        ])
        self.assertTrue(sim.select_group("single"))
        self.assertTrue(sim.record_shots("single", 2))
        self.assertTrue(sim.tick(5))
        self.assertEqual(sim.returned_ids, ["single"])
        self.assertEqual(sim.storage_occupied, 1)

    def test_full_storage_causes_failure_at_return(self):
        sim = create_simulator(
            [{"id": "single", "group_id": "single", "ammo": 1}],
            storage_occupied=5,
        )
        self.assertTrue(sim.select_group("single"))
        self.assertTrue(sim.record_shots("single", 1))
        self.assertFalse(sim.tick(5))
        self.assertTrue(sim.failed)
        self.assertIn("STORAGE_IS_FULL", sim.failure_reason)

    def test_shooter_with_ammo_keeps_rotating(self):
        sim = create_simulator([
            {"id": "single", "group_id": "single", "ammo": 10}
        ])
        sim.select_group("single")
        self.assertTrue(sim.tick(5))
        self.assertEqual(sim.active[0].completed_laps, 1)
        self.assertEqual(sim.storage_occupied, 0)

    def test_cannot_record_more_shots_than_ammo(self):
        sim = create_simulator([
            {"id": "single", "group_id": "single", "ammo": 3}
        ])
        sim.select_group("single")
        self.assertFalse(sim.record_shots("single", 4))
        self.assertEqual(sim.active[0].ammo, 3)

    def test_report_never_enables_live_actions(self):
        sim = create_simulator([
            {"id": "single", "group_id": "single", "ammo": 3}
        ])
        report = sim.report()
        self.assertTrue(report["simulation_only"])
        self.assertFalse(report["live_actions_performed"])
        self.assertFalse(report["live_taps_enabled"])



    def test_custom_ticks_per_lap_controls_return_timing(self):
        from conveyor_simulator import (
            ConveyorSimulator, Shooter, SimulatorConfig
        )
        sim = ConveyorSimulator(
            shooters=[Shooter("custom_a", "custom_group", 0)],
            config=SimulatorConfig(ticks_per_lap=3)
        )
        self.assertTrue(sim.select_group("custom_group"))
        self.assertTrue(sim.tick(2))
        self.assertEqual(sim.returned_ids, [])
        self.assertTrue(sim.tick(1))
        self.assertEqual(sim.returned_ids, ["custom_a"])
        self.assertEqual(sim.report()["ticks_per_lap"], 3)

if __name__ == "__main__":
    unittest.main()
