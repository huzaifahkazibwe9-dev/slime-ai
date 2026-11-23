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

    def test_reactivation_preserves_zero_ammo_and_group_identity(self):
        sim = create_simulator([
            {"id": "A1", "group_id": "PAIR", "ammo": 0},
            {"id": "A2", "group_id": "PAIR", "ammo": 0},
        ], config=SimulatorConfig(conveyor_capacity=2, ticks_per_lap=2))
        self.assertTrue(sim.select_group("PAIR"))
        self.assertTrue(sim.tick(2))
        self.assertEqual(sim.storage_occupied, 2)
        self.assertTrue(sim.reactivate_group("PAIR"))
        self.assertEqual(sim.storage_occupied, 0)
        self.assertEqual(
            {s.shooter_id: s.ammo for s in sim.shooters},
            {"A1": 0, "A2": 0},
        )
        self.assertEqual(
            {s.group_id for s in sim.shooters},
            {"PAIR"},
        )
        self.assertEqual(len(sim.active), 0)
        self.assertTrue(sim.select_group("PAIR"))
        self.assertEqual({s.ammo for s in sim.active}, {0})
        self.assertEqual(len(sim.active), 2)

    def test_reactivation_rejects_partial_group_without_mutation(self):
        sim = create_simulator([
            {"id": "A1", "group_id": "PAIR", "ammo": 0},
            {"id": "A2", "group_id": "PAIR", "ammo": 0},
        ], config=SimulatorConfig(conveyor_capacity=2, ticks_per_lap=2))
        self.assertTrue(sim.select_group("PAIR"))
        self.assertTrue(sim.record_shots("A1", 0))
        # Complete and return both, then corrupt one member's return state
        # to model inconsistent persisted observations.
        self.assertTrue(sim.tick(2))
        sim.shooters[1].returned = False
        before = (sim.storage_occupied, [
            (x.shooter_id, x.returned, x.selected, x.ammo)
            for x in sim.shooters
        ])
        self.assertFalse(sim.reactivate_group("PAIR"))
        after = (sim.storage_occupied, [
            (x.shooter_id, x.returned, x.selected, x.ammo)
            for x in sim.shooters
        ])
        self.assertEqual(after, before)

    def test_config_rejects_boolean_or_fractional_tick_counts(self):
        for value in (True, 2.5, 0, -1):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    SimulatorConfig(ticks_per_lap=value)

    def test_shooter_rejects_invalid_position_and_boolean_ammo(self):
        for kwargs in (
            {"position": -1}, {"position": 5}, {"ammo": True},
            {"completed_laps": -1}, {"selected": 1},
        ):
            with self.subTest(kwargs=kwargs):
                values = {"shooter_id": "s", "group_id": "g", "ammo": 3}
                values.update(kwargs)
                with self.assertRaises(ValueError):
                    Shooter(**values)

    def test_factory_does_not_coerce_malformed_state_records(self):
        malformed = [
            {"id": "s", "ammo": True},
            {"id": "s", "ammo": 3, "selected": "false"},
            {"id": "s", "ammo": 3, "position": 1.8},
        ]
        for record in malformed:
            with self.subTest(record=record):
                with self.assertRaises((ValueError, TypeError)):
                    create_simulator([record])

    def test_factory_accepts_returned_storage_record(self):
        sim = create_simulator([
            {"id": "stored", "ammo": 0, "returned": True}
        ], storage_occupied=1)
        self.assertEqual(sim.active, [])
        self.assertEqual(sim.returned_ids, [])
        self.assertEqual(sim.storage_occupied, 1)

    def test_simulator_rejects_position_outside_lap(self):
        with self.assertRaises(ValueError):
            ConveyorSimulator(
                shooters=[Shooter("s", "g", 1, position=5)],
                config=SimulatorConfig(ticks_per_lap=5),
            )

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
