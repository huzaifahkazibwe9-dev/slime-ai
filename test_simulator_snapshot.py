import copy
import unittest

from conveyor_simulator import SimulatorConfig, create_simulator
from simulator_snapshot import restore_simulator, snapshot_simulator


class SimulatorSnapshotTests(unittest.TestCase):
    def test_round_trip_preserves_state_events_and_tick_count(self):
        sim = create_simulator([
            {"id": "a", "ammo": 0},
            {"id": "b", "ammo": 4},
        ], config=SimulatorConfig(ticks_per_lap=2))
        self.assertTrue(sim.select_group("a"))
        self.assertTrue(sim.record_shots("a", 0))
        self.assertTrue(sim.tick(2))

        restored = restore_simulator(snapshot_simulator(sim))
        self.assertEqual(restored.tick_count, sim.tick_count)
        self.assertEqual(restored.events, sim.events)
        self.assertEqual(restored.returned_ids, sim.returned_ids)
        self.assertEqual(restored.storage_occupied, sim.storage_occupied)
        self.assertEqual(
            [(s.shooter_id, s.ammo, s.position, s.completed_laps,
              s.selected, s.returned) for s in restored.shooters],
            [(s.shooter_id, s.ammo, s.position, s.completed_laps,
              s.selected, s.returned) for s in sim.shooters],
        )

    def test_round_trip_preserves_failed_partial_tick_history(self):
        sim = create_simulator(
            [{"id": "first", "ammo": 0}, {"id": "second", "ammo": 0}],
            storage_occupied=4,
            config=SimulatorConfig(storage_capacity=5, ticks_per_lap=1),
        )
        self.assertTrue(sim.select_group("first"))
        self.assertTrue(sim.select_group("second"))
        self.assertFalse(sim.tick(1))

        restored = restore_simulator(snapshot_simulator(sim))
        self.assertTrue(restored.failed)
        self.assertEqual(restored.failure_reason, sim.failure_reason)
        self.assertEqual(restored.tick_count, 1)
        self.assertEqual(restored.returned_ids, ["first"])
        self.assertEqual(restored.storage_occupied, 5)
        self.assertEqual(restored.events, sim.events)

    def test_snapshot_is_detached_from_later_mutations(self):
        sim = create_simulator([{"id": "a", "ammo": 3}])
        snapshot = snapshot_simulator(sim)
        sim.events.append({"tick": 0, "event": "LATER"})
        self.assertEqual(snapshot["events"], [])

    def test_snapshot_rejects_non_json_event_values(self):
        sim = create_simulator([{"id": "a", "ammo": 3}])
        sim.events.append({"tick": 0, "event": "CUSTOM", "value": object()})
        with self.assertRaises(ValueError):
            snapshot_simulator(sim)

    def test_restore_rejects_non_finite_json_numbers(self):
        snapshot = snapshot_simulator(create_simulator([{"id": "a", "ammo": 3}]))
        snapshot["events"] = [
            {"tick": 0, "event": "CUSTOM", "value": float("nan")}
        ]
        with self.assertRaises(ValueError):
            restore_simulator(snapshot)

    def test_rejects_storage_occupancy_below_returned_shooters(self):
        sim = create_simulator([
            {"id": "a", "ammo": 0, "returned": True},
        ], storage_occupied=1)
        snapshot = snapshot_simulator(sim)
        snapshot["storage_occupied"] = 0
        with self.assertRaises(ValueError):
            restore_simulator(snapshot)

    def test_rejects_inconsistent_returned_ids(self):
        snapshot = snapshot_simulator(create_simulator([
            {"id": "a", "ammo": 0, "returned": True},
        ], storage_occupied=1))
        snapshot["returned_ids"] = []
        with self.assertRaises(ValueError):
            restore_simulator(snapshot)

    def test_rejects_event_beyond_snapshot_tick(self):
        snapshot = snapshot_simulator(create_simulator([{"id": "a", "ammo": 3}]))
        snapshot["events"] = [{"tick": 1, "event": "SHOOTER_ROTATED"}]
        with self.assertRaises(ValueError):
            restore_simulator(snapshot)

    def test_rejects_out_of_order_event_ticks(self):
        snapshot = snapshot_simulator(create_simulator([{"id": "a", "ammo": 3}]))
        snapshot["tick_count"] = 2
        snapshot["events"] = [
            {"tick": 2, "event": "SHOOTER_ROTATED"},
            {"tick": 1, "event": "AMMO_UPDATED"},
        ]
        with self.assertRaises(ValueError):
            restore_simulator(snapshot)

    def test_rejects_event_reference_to_unknown_shooter(self):
        snapshot = snapshot_simulator(create_simulator([{"id": "a", "ammo": 3}]))
        snapshot["events"] = [
            {"tick": 0, "event": "SHOOTER_ROTATED", "shooter_id": "missing"}
        ]
        with self.assertRaises(ValueError):
            restore_simulator(snapshot)

    def test_rejects_duplicate_return_events(self):
        snapshot = snapshot_simulator(create_simulator([
            {"id": "a", "ammo": 0, "selected": True, "returned": True}
        ], storage_occupied=1))
        snapshot["returned_ids"] = ["a"]
        snapshot["events"] = [
            {"tick": 1, "event": "SHOOTER_RETURNED_TO_STORAGE", "shooter_id": "a"},
            {"tick": 2, "event": "SHOOTER_RETURNED_TO_STORAGE", "shooter_id": "a"},
        ]
        snapshot["tick_count"] = 2
        with self.assertRaises(ValueError):
            restore_simulator(snapshot)

    def test_rejects_return_event_order_conflicting_with_returned_ids(self):
        snapshot = snapshot_simulator(create_simulator([
            {"id": "a", "ammo": 0, "selected": True, "returned": True},
            {"id": "b", "ammo": 0, "selected": True, "returned": True},
        ], storage_occupied=2))
        snapshot["returned_ids"] = ["b", "a"]
        snapshot["events"] = [
            {"tick": 1, "event": "SHOOTER_RETURNED_TO_STORAGE", "shooter_id": "a"},
            {"tick": 2, "event": "SHOOTER_RETURNED_TO_STORAGE", "shooter_id": "b"},
        ]
        snapshot["tick_count"] = 2
        with self.assertRaises(ValueError):
            restore_simulator(snapshot)

    def test_rejects_non_boolean_shooter_state_flags(self):
        snapshot = snapshot_simulator(create_simulator([{"id": "a", "ammo": 3}]))
        snapshot["shooters"][0]["selected"] = "true"
        with self.assertRaises(ValueError):
            restore_simulator(snapshot)

    def test_rejects_nonfailed_snapshot_ending_in_failure_event(self):
        snapshot = snapshot_simulator(create_simulator([{"id": "a", "ammo": 3}]))
        snapshot["events"] = [{"tick": 0, "event": "LEVEL_FAILURE", "reason": "x"}]
        with self.assertRaises(ValueError):
            restore_simulator(snapshot)

    def test_rejects_failed_flag_without_failure_reason(self):
        snapshot = snapshot_simulator(create_simulator([{"id": "a", "ammo": 3}]))
        snapshot["failed"] = True
        with self.assertRaises(ValueError):
            restore_simulator(snapshot)

    def test_rejects_unknown_schema_and_live_action_flags(self):
        original = snapshot_simulator(create_simulator([{"id": "a", "ammo": 3}]))
        for key, value in (("schema_version", 99), ("live_taps_enabled", True),
                           ("live_actions_performed", True)):
            snapshot = copy.deepcopy(original)
            snapshot[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                restore_simulator(snapshot)


if __name__ == "__main__":
    unittest.main(verbosity=2)
