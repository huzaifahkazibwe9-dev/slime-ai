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
            restored.initial_storage_occupied, sim.initial_storage_occupied
        )
        self.assertEqual(
            [(s.shooter_id, s.ammo, s.position, s.completed_laps,
              s.selected, s.returned) for s in restored.shooters],
            [(s.shooter_id, s.ammo, s.position, s.completed_laps,
              s.selected, s.returned) for s in sim.shooters],
        )

    def test_round_trip_preserves_unverified_observation_quality(self):
        quality = {
            "colour_independently_verified": False,
            "ammunition_independently_verified": False,
            "slot_mapping_independently_verified": False,
            "evidence_source": "detector_declared",
            "ammunition_ocr_status": "PARSED_EXACT_DIGITS",
        }
        sim = create_simulator([{
            "id": "a", "ammo": 3, "observation_quality": quality,
        }])
        restored = restore_simulator(snapshot_simulator(sim))
        self.assertEqual(restored.shooters[0].observation_quality, quality)
        self.assertEqual(
            snapshot_simulator(restored)["shooters"][0]["observation_quality"],
            quality,
        )

    def test_simulator_report_exposes_visual_evidence_as_unverified(self):
        sim = create_simulator([{"id": "a", "ammo": 3}])
        report = sim.report()
        expected = {
            "colour_independently_verified": False,
            "ammunition_independently_verified": False,
            "slot_mapping_independently_verified": False,
            "ammunition_ocr_status": "NOT_REPORTED",
        }
        self.assertEqual(report["shooter_observation_quality"], [
            {"id": "a", **expected}
        ])
        sim.select_group("a")
        self.assertEqual(
            sim.report()["active_shooters"][0]["observation_quality"],
            expected,
        )

    def test_simulator_rejects_unsubstantiated_visual_verification(self):
        for flag in (
            "colour_independently_verified",
            "ammunition_independently_verified",
            "slot_mapping_independently_verified",
        ):
            with self.subTest(flag=flag):
                with self.assertRaisesRegex(ValueError, "independent evidence"):
                    create_simulator([{
                        "id": "a", "ammo": 3,
                        "observation_quality": {flag: True},
                    }])

    def test_restore_rejects_tampered_detector_declared_ocr_status(self):
        sim = create_simulator([{
            "id": "a",
            "ammo": 3,
            "observation_quality": {
                "evidence_source": "detector_declared",
                "ammunition_ocr_status": "PARSED_EXACT_DIGITS",
            },
        }])
        snapshot = snapshot_simulator(sim)
        snapshot["shooters"][0]["observation_quality"][
            "ammunition_ocr_status"
        ] = "TESSERACT_TIMEOUT"
        with self.assertRaisesRegex(ValueError, "successful ammunition OCR"):
            restore_simulator(snapshot)

    def test_legacy_snapshot_defaults_observation_quality_to_unverified(self):
        snapshot = snapshot_simulator(
            create_simulator([{"id": "a", "ammo": 3}])
        )
        snapshot["shooters"][0].pop("observation_quality")
        restored = restore_simulator(snapshot)
        self.assertEqual(restored.shooters[0].observation_quality, {})
        self.assertIs(
            restored.shooters[0].observation_quality.get(
                "colour_independently_verified", False
            ),
            False,
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

    def test_round_trip_preserves_bonded_returns_before_later_group_tick_failure(self):
        sim = create_simulator(
            [
                {"id": "pair-a", "group_id": "PAIR", "ammo": 0},
                {"id": "pair-b", "group_id": "PAIR", "ammo": 0},
                {"id": "solo", "group_id": "SOLO", "ammo": 0},
            ],
            storage_occupied=1,
            config=SimulatorConfig(storage_capacity=3, ticks_per_lap=1),
        )
        self.assertTrue(sim.select_group("PAIR"))
        self.assertTrue(sim.select_group("SOLO"))
        self.assertFalse(sim.tick(1))

        self.assertTrue(sim.failed)
        self.assertEqual(sim.returned_ids, ["pair-a", "pair-b"])
        self.assertEqual(sim.storage_occupied, 3)
        self.assertEqual(sim.tick_count, 1)
        return_events = [
            event for event in sim.events
            if event["event"] == "SHOOTER_RETURNED_TO_STORAGE"
        ]
        self.assertEqual(
            [event["shooter_id"] for event in return_events],
            ["pair-a", "pair-b"],
        )
        self.assertEqual(sim.events[-1]["event"], "LEVEL_FAILURE")

        restored = restore_simulator(snapshot_simulator(sim))
        self.assertTrue(restored.failed)
        self.assertEqual(restored.failure_reason, sim.failure_reason)
        self.assertEqual(restored.tick_count, sim.tick_count)
        self.assertEqual(restored.returned_ids, sim.returned_ids)
        self.assertEqual(restored.storage_occupied, sim.storage_occupied)
        self.assertEqual(restored.events, sim.events)
        self.assertEqual(
            [(s.shooter_id, s.selected, s.returned) for s in restored.shooters],
            [(s.shooter_id, s.selected, s.returned) for s in sim.shooters],
        )

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

    def test_rejects_latest_storage_event_occupancy_mismatch(self):
        sim = create_simulator(
            [{"id": "a", "ammo": 0}],
            config=SimulatorConfig(storage_capacity=2, ticks_per_lap=1),
        )
        self.assertTrue(sim.select_group("a"))
        self.assertTrue(sim.tick(1))
        snapshot = snapshot_simulator(sim)
        return_event = next(
            event for event in snapshot["events"]
            if event.get("event") == "SHOOTER_RETURNED_TO_STORAGE"
        )
        snapshot["initial_storage_occupied"] = 1
        return_event["storage_occupied"] = 2
        return_event["storage_free"] = 0
        with self.assertRaisesRegex(ValueError, "disagrees with restored occupancy"):
            restore_simulator(snapshot)

    def test_rejects_inconsistent_storage_free_in_return_event(self):
        sim = create_simulator(
            [{"id": "a", "ammo": 0}],
            config=SimulatorConfig(storage_capacity=3, ticks_per_lap=1),
        )
        self.assertTrue(sim.select_group("a"))
        self.assertTrue(sim.tick(1))
        snapshot = snapshot_simulator(sim)
        return_event = next(
            event for event in snapshot["events"]
            if event.get("event") == "SHOOTER_RETURNED_TO_STORAGE"
        )
        return_event["storage_free"] = 3
        with self.assertRaisesRegex(ValueError, "storage_free is inconsistent"):
            restore_simulator(snapshot)

    def test_rejects_forged_first_storage_event_from_initial_occupancy(self):
        sim = create_simulator(
            [{"id": "a", "ammo": 0}],
            storage_occupied=1,
            config=SimulatorConfig(storage_capacity=3, ticks_per_lap=1),
        )
        self.assertTrue(sim.select_group("a"))
        self.assertTrue(sim.tick(1))
        snapshot = snapshot_simulator(sim)
        self.assertEqual(snapshot["initial_storage_occupied"], 1)
        self.assertEqual(snapshot["storage_occupied"], 2)
        return_event = next(
            event for event in snapshot["events"]
            if event.get("event") == "SHOOTER_RETURNED_TO_STORAGE"
        )
        # Keep the final state and event mutually consistent, but forge the
        # first transition so it fails to account for the initial occupancy.
        return_event["storage_occupied"] = 1
        snapshot["storage_occupied"] = 1
        with self.assertRaisesRegex(ValueError, "occupancy event delta"):
            restore_simulator(snapshot)

    def test_rejects_invalid_storage_occupancy_in_event(self):
        sim = create_simulator(
            [{"id": "a", "ammo": 0}],
            config=SimulatorConfig(storage_capacity=2, ticks_per_lap=1),
        )
        self.assertTrue(sim.select_group("a"))
        self.assertTrue(sim.tick(1))
        snapshot = snapshot_simulator(sim)
        return_event = next(
            event for event in snapshot["events"]
            if event.get("event") == "SHOOTER_RETURNED_TO_STORAGE"
        )
        return_event["storage_occupied"] = True
        with self.assertRaisesRegex(ValueError, "invalid storage occupancy"):
            restore_simulator(snapshot)

    def test_rejects_inconsistent_storage_occupancy_delta(self):
        sim = create_simulator(
            [
                {"id": "a", "ammo": 0},
                {"id": "b", "ammo": 0},
            ],
            config=SimulatorConfig(storage_capacity=2, ticks_per_lap=1),
        )
        self.assertTrue(sim.select_group("a"))
        self.assertTrue(sim.select_group("b"))
        self.assertTrue(sim.tick(1))
        snapshot = snapshot_simulator(sim)
        returns = [
            event for event in snapshot["events"]
            if event.get("event") == "SHOOTER_RETURNED_TO_STORAGE"
        ]
        self.assertEqual([event["storage_occupied"] for event in returns], [1, 2])
        returns[1]["storage_occupied"] = 1
        with self.assertRaisesRegex(ValueError, "occupancy event delta"):
            restore_simulator(snapshot)

    def test_rejects_reactivation_event_with_invalid_members_for_occupancy(self):
        sim = create_simulator(
            [{"id": "a", "ammo": 0}],
            config=SimulatorConfig(storage_capacity=1, ticks_per_lap=1),
        )
        self.assertTrue(sim.select_group("a"))
        self.assertTrue(sim.tick(1))
        self.assertTrue(sim.reactivate_group("a"))
        snapshot = snapshot_simulator(sim)
        event = next(
            event for event in snapshot["events"]
            if event.get("event") == "GROUP_REACTIVATED_FROM_STORAGE"
        )
        event["members"] = "a"
        with self.assertRaisesRegex(ValueError, "must list its group members"):
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

    def test_restore_rejects_bonded_group_larger_than_three(self):
        snapshot = snapshot_simulator(create_simulator([
            {"id": "a1", "group_id": "GROUP", "ammo": 2},
            {"id": "a2", "group_id": "GROUP", "ammo": 2},
            {"id": "a3", "group_id": "GROUP", "ammo": 2},
        ]))
        snapshot["shooters"].append({
            "id": "a4",
            "group_id": "GROUP",
            "ammo": 2,
            "position": 0,
            "completed_laps": 0,
            "selected": False,
            "returned": False,
        })
        with self.assertRaisesRegex(ValueError, "maximum size of 3"):
            restore_simulator(snapshot)

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
        with self.assertRaisesRegex(ValueError, "return history is incomplete|storage event disagrees"):
            restore_simulator(snapshot)

    def test_rejects_partial_historical_return_before_reactivation(self):
        sim = create_simulator(
            [
                {"id": "a1", "group_id": "PAIR", "ammo": 0},
                {"id": "a2", "group_id": "PAIR", "ammo": 0},
            ],
            config=SimulatorConfig(storage_capacity=2, ticks_per_lap=1),
        )
        self.assertTrue(sim.select_group("PAIR"))
        self.assertTrue(sim.tick(1))
        self.assertTrue(sim.reactivate_group("PAIR"))
        snapshot = snapshot_simulator(sim)
        snapshot["events"] = [
            event for event in snapshot["events"]
            if not (
                event.get("event") == "SHOOTER_RETURNED_TO_STORAGE"
                and event.get("shooter_id") == "a2"
            )
        ]
        with self.assertRaisesRegex(
            ValueError,
            "return history is incomplete|storage occupancy event delta is inconsistent|storage occupancy event delta is out of range",
        ):
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

    def test_rejects_failure_event_inside_nonfailed_snapshot_history(self):
        snapshot = snapshot_simulator(create_simulator([{"id": "a", "ammo": 3}]))
        snapshot["events"] = [
            {"tick": 0, "event": "LEVEL_FAILURE", "reason": "premature"},
            {"tick": 0, "event": "SHOOTER_ENTERED",
             "shooter_id": "a", "group_id": "a", "position": 0},
        ]
        with self.assertRaisesRegex(
            ValueError, "non-failed snapshot cannot contain a LEVEL_FAILURE event"
        ):
            restore_simulator(snapshot)

    def test_rejects_duplicate_or_nonterminal_failure_event(self):
        sim = create_simulator(
            [{"id": "a", "ammo": 0}],
            storage_occupied=1,
            config=SimulatorConfig(storage_capacity=1, ticks_per_lap=1),
        )
        self.assertTrue(sim.select_group("a"))
        self.assertFalse(sim.tick(1))
        snapshot = snapshot_simulator(sim)
        self.assertTrue(snapshot["failed"])
        snapshot["events"].insert(
            len(snapshot["events"]) - 1,
            copy.deepcopy(snapshot["events"][-1]),
        )
        with self.assertRaisesRegex(
            ValueError,
            "failed snapshot must contain exactly one final LEVEL_FAILURE event",
        ):
            restore_simulator(snapshot)

    def test_rejects_failure_event_tick_before_final_simulator_tick(self):
        sim = create_simulator(
            [{"id": "a", "ammo": 0}],
            storage_occupied=1,
            config=SimulatorConfig(storage_capacity=1, ticks_per_lap=1),
        )
        self.assertTrue(sim.select_group("a"))
        self.assertFalse(sim.tick(1))
        snapshot = snapshot_simulator(sim)
        self.assertTrue(snapshot["failed"])
        self.assertGreater(snapshot["tick_count"], 0)
        snapshot["tick_count"] += 1
        with self.assertRaisesRegex(
            ValueError, "failure event tick must match the final simulator tick"
        ):
            restore_simulator(snapshot)

    def test_rejects_failed_flag_without_failure_reason(self):
        snapshot = snapshot_simulator(create_simulator([{"id": "a", "ammo": 3}]))
        snapshot["failed"] = True
        with self.assertRaises(ValueError):
            restore_simulator(snapshot)

    def test_rejects_unknown_event_type(self):
        snapshot = snapshot_simulator(create_simulator([{"id": "a", "ammo": 3}]))
        snapshot["events"] = [
            {"tick": 0, "event": "UNRECOGNIZED_FUTURE_EVENT"}
        ]
        with self.assertRaisesRegex(ValueError, "unsupported event type"):
            restore_simulator(snapshot)

    def test_rejects_unknown_schema_and_live_action_flags(self):
        original = snapshot_simulator(create_simulator([{"id": "a", "ammo": 3}]))
        for key, value in (("schema_version", 99), ("schema_version", True), ("live_taps_enabled", True),
                           ("live_actions_performed", True)):
            snapshot = copy.deepcopy(original)
            snapshot[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                restore_simulator(snapshot)



    def test_rejects_event_missing_required_payload_field(self):
        snapshot = snapshot_simulator(create_simulator([{"id": "a", "ammo": 3}]))
        snapshot["events"] = [
            {"tick": 0, "event": "SHOOTER_ROTATED", "shooter_id": "a"}
        ]
        with self.assertRaisesRegex(
            ValueError, "SHOOTER_ROTATED event is missing required fields: position"
        ):
            restore_simulator(snapshot)

    def test_rejects_boolean_event_position(self):
        snapshot = snapshot_simulator(create_simulator([{"id": "a", "ammo": 3}]))
        snapshot["events"] = [
            {
                "tick": 0,
                "event": "SHOOTER_ROTATED",
                "shooter_id": "a",
                "position": True,
            }
        ]
        with self.assertRaisesRegex(ValueError, "invalid position"):
            restore_simulator(snapshot)

    def test_rejects_event_position_outside_configured_lap(self):
        snapshot = snapshot_simulator(create_simulator(
            [{"id": "a", "ammo": 3}],
            config=SimulatorConfig(ticks_per_lap=2),
        ))
        snapshot["events"] = [
            {
                "tick": 0,
                "event": "SHOOTER_ROTATED",
                "shooter_id": "a",
                "position": 2,
            }
        ]
        with self.assertRaisesRegex(ValueError, "position is outside the lap"):
            restore_simulator(snapshot)

    def test_rejects_event_group_that_conflicts_with_shooter(self):
        snapshot = snapshot_simulator(create_simulator([
            {"id": "a", "group_id": "PAIR", "ammo": 3}
        ]))
        snapshot["events"] = [
            {
                "tick": 0,
                "event": "SHOOTER_ENTERED",
                "shooter_id": "a",
                "group_id": "OTHER",
                "position": 0,
            }
        ]
        with self.assertRaisesRegex(ValueError, "group does not match shooter"):
            restore_simulator(snapshot)

    def test_rejects_unexpected_event_payload_fields(self):
        snapshot = snapshot_simulator(create_simulator([{"id": "a", "ammo": 3}]))
        snapshot["events"] = [
            {
                "tick": 0,
                "event": "SHOOTER_ROTATED",
                "shooter_id": "a",
                "position": 0,
                "unreviewed_metadata": "not part of schema",
            }
        ]
        with self.assertRaisesRegex(ValueError, "unsupported fields"):
            restore_simulator(snapshot)

    def test_round_trip_preserves_selection_rejection_for_unknown_group(self):
        sim = create_simulator([{"id": "a", "ammo": 3}])
        self.assertFalse(sim.select_group("missing"))
        restored = restore_simulator(snapshot_simulator(sim))
        self.assertEqual(restored.events, sim.events)


if __name__ == "__main__":
    unittest.main(verbosity=2)
