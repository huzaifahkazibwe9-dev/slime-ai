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

    def test_rejects_non_string_event_shooter_reference(self):
        snapshot = snapshot_simulator(create_simulator([{"id": "a", "ammo": 3}]))
        snapshot["events"] = [
            {"tick": 0, "event": "CUSTOM", "shooter_id": ["a"]}
        ]
        with self.assertRaises(ValueError):
            restore_simulator(snapshot)

    def test_rejects_non_string_event_group_member(self):
        snapshot = snapshot_simulator(create_simulator([
            {"id": "a", "ammo": 3}
        ]))
        snapshot["events"] = [
            {"tick": 0, "event": "CUSTOM", "members": [["a"]]}
        ]
        with self.assertRaises(ValueError):
            restore_simulator(snapshot)

    def test_round_trip_allows_shooter_to_return_after_storage_reactivation(self):
        sim = create_simulator(
            [{"id": "a", "group_id": "A", "ammo": 0}],
            config=SimulatorConfig(storage_capacity=2, ticks_per_lap=1),
        )
        self.assertTrue(sim.select_group("A"))
        self.assertTrue(sim.tick(1))
        self.assertEqual(sim.returned_ids, ["a"])
        self.assertTrue(sim.reactivate_group("A"))
        self.assertTrue(sim.select_group("A"))
        self.assertTrue(sim.tick(1))
        self.assertEqual(sim.returned_ids, ["a"])

        restored = restore_simulator(snapshot_simulator(sim))
        self.assertEqual(restored.returned_ids, ["a"])
        self.assertEqual(restored.events, sim.events)
        return_events = [
            event for event in restored.events
            if event["event"] == "SHOOTER_RETURNED_TO_STORAGE"
        ]
        self.assertEqual(len(return_events), 2)

    def test_rejects_incomplete_bonded_group_reactivation_events(self):
        base = snapshot_simulator(create_simulator([
            {"id": "a1", "group_id": "PAIR", "ammo": 0,
             "selected": True, "returned": True},
            {"id": "a2", "group_id": "PAIR", "ammo": 0,
             "selected": True, "returned": True},
        ], storage_occupied=2))
        base["tick_count"] = 1
        invalid_events = [
            [{
                "tick": 1,
                "event": "GROUP_REACTIVATED_FROM_STORAGE",
                "group_id": "PAIR",
            }],
            [{
                "tick": 1,
                "event": "GROUP_REACTIVATED_FROM_STORAGE",
                "group_id": "PAIR",
                "members": ["a1"],
            }],
            [{
                "tick": 1,
                "event": "GROUP_REACTIVATED_FROM_STORAGE",
                "group_id": "WRONG",
                "members": ["a1", "a2"],
            }],
        ]
        for events in invalid_events:
            with self.subTest(events=events):
                snapshot = copy.deepcopy(base)
                snapshot["events"] = events
                with self.assertRaises(ValueError):
                    restore_simulator(snapshot)

    def _completed_bonded_snapshot(self):
        sim = create_simulator(
            [
                {"id": "a1", "group_id": "PAIR", "ammo": 0},
                {"id": "a2", "group_id": "PAIR", "ammo": 0},
            ],
            config=SimulatorConfig(storage_capacity=2, ticks_per_lap=1),
        )
        self.assertTrue(sim.select_group("PAIR"))
        self.assertTrue(sim.tick(1))
        return snapshot_simulator(sim)

    def test_rejects_partial_bonded_group_return_history(self):
        snapshot = self._completed_bonded_snapshot()
        snapshot["events"] = [
            event for event in snapshot["events"]
            if not (
                event.get("event") == "SHOOTER_RETURNED_TO_STORAGE"
                and event.get("shooter_id") == "a2"
            )
        ]
        with self.assertRaisesRegex(ValueError, "return history is incomplete"):
            restore_simulator(snapshot)

    def test_rejects_bonded_group_return_events_on_different_ticks(self):
        snapshot = self._completed_bonded_snapshot()
        return_events = [
            event for event in snapshot["events"]
            if event.get("event") == "SHOOTER_RETURNED_TO_STORAGE"
        ]
        return_events[1]["tick"] = 2
        snapshot["tick_count"] = 2
        with self.assertRaisesRegex(ValueError, "must share a tick"):
            restore_simulator(snapshot)

    def test_rejects_active_shooter_with_unreconciled_return_event(self):
        snapshot = snapshot_simulator(create_simulator([
            {"id": "a", "group_id": "A", "ammo": 0}
        ]))
        snapshot["tick_count"] = 1
        snapshot["events"] = [
            {"tick": 1, "event": "SHOOTER_RETURNED_TO_STORAGE",
             "shooter_id": "a"}
        ]
        with self.assertRaises(ValueError):
            restore_simulator(snapshot)

    def test_round_trip_allows_active_shooter_after_reactivation(self):
        sim = create_simulator(
            [{"id": "a", "group_id": "A", "ammo": 0}],
            config=SimulatorConfig(storage_capacity=2, ticks_per_lap=1),
        )
        self.assertTrue(sim.select_group("A"))
        self.assertTrue(sim.tick(1))
        self.assertTrue(sim.reactivate_group("A"))
        snapshot = snapshot_simulator(sim)

        restored = restore_simulator(snapshot)
        self.assertFalse(restored.shooters[0].returned)
        self.assertEqual(restored.events, sim.events)

    def test_rejects_return_event_that_precedes_latest_reactivation(self):
        snapshot = snapshot_simulator(create_simulator([
            {"id": "a", "group_id": "A", "ammo": 0, "selected": True, "returned": True}
        ], storage_occupied=1))
        snapshot["returned_ids"] = ["a"]
        snapshot["tick_count"] = 2
        snapshot["events"] = [
            {"tick": 1, "event": "SHOOTER_RETURNED_TO_STORAGE", "shooter_id": "a"},
            {"tick": 2, "event": "GROUP_REACTIVATED_FROM_STORAGE",
             "group_id": "A", "members": ["a"]},
        ]
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
