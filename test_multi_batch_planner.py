import unittest
from unittest.mock import patch
from multi_batch_planner import simulate_batch_schedule
from conveyor_simulator import SimulatorConfig


class MultiBatchTests(unittest.TestCase):
    def test_invalid_config_type_is_rejected(self):
        for config in (False, "not-a-config"):
            with self.subTest(config=config):
                result = simulate_batch_schedule(
                    [{"id": "A", "group_id": "A", "ammo": 1}],
                    [],
                    config=config,
                )
                self.assertFalse(result["schedule_valid"])
                self.assertEqual(
                    result["failure_reason"],
                    "CONFIG_MUST_BE_SIMULATOR_CONFIG",
                )
                self.assertFalse(result["live_execution_allowed"])

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

    def test_multiple_reactivations_preflight_total_conveyor_capacity(self):
        records = [
            {"id": "A1", "group_id": "PAIR_A", "ammo": 0},
            {"id": "A2", "group_id": "PAIR_A", "ammo": 0},
            {"id": "B1", "group_id": "PAIR_B", "ammo": 0},
            {"id": "B2", "group_id": "PAIR_B", "ammo": 0},
            {"id": "C", "group_id": "C", "ammo": 1},
        ]
        r = simulate_batch_schedule(
            records,
            [
                {"groups": ["PAIR_A"], "shots": {"A1": 0, "A2": 0}},
                {"groups": ["PAIR_B"], "shots": {"B1": 0, "B2": 0}},
                {
                    "groups": ["C"],
                    "reactivate_groups": ["PAIR_A", "PAIR_B"],
                    "shots": {"C": 0},
                },
            ],
            config=SimulatorConfig(
                conveyor_capacity=4, storage_capacity=5, ticks_per_lap=1
            ),
            allow_storage_reactivation=True,
        )
        self.assertFalse(r["schedule_valid"])
        self.assertEqual(
            r["batch_reports"][-1]["reason"],
            "INSUFFICIENT_CONVEYOR_SPACE_FOR_BATCH_TRANSITION",
        )
        self.assertEqual(r["returned_shooters"], ["A1", "A2", "B1", "B2"])

    def test_reactivated_group_can_be_selected_in_same_batch(self):
        r = simulate_batch_schedule(
            [{"id": "A", "group_id": "A", "ammo": 0}],
            [
                {"groups": ["A"], "shots": {"A": 0}},
                {
                    "groups": ["A"],
                    "reactivate_groups": ["A"],
                    "shots": {"A": 0},
                },
            ],
            config=SimulatorConfig(ticks_per_lap=1),
            allow_storage_reactivation=True,
        )
        self.assertTrue(r["schedule_valid"])
        self.assertEqual(r["batches_completed"], 2)
        self.assertEqual(r["returned_shooters"], ["A"])


    def test_non_iterable_batches_are_rejected_without_crashing(self):
        r = simulate_batch_schedule(
            [{"id": "A", "group_id": "A", "ammo": 1}],
            None,
        )
        self.assertFalse(r["schedule_valid"])
        self.assertEqual(
            r["batch_reports"][0]["reason"],
            "BATCHES_MUST_BE_ITERABLE",
        )
        self.assertEqual(r["batches_completed"], 0)
        self.assertEqual(r["conveyor_occupied"], 0)

    def test_non_mapping_batch_is_rejected_without_crashing(self):
        r = simulate_batch_schedule(
            [{"id": "A", "group_id": "A", "ammo": 1}],
            [None],
        )
        self.assertFalse(r["schedule_valid"])
        self.assertEqual(
            r["batch_reports"][-1]["reason"],
            "BATCH_MUST_BE_A_MAPPING",
        )
        self.assertEqual(r["batches_completed"], 0)
        self.assertEqual(r["conveyor_occupied"], 0)

    def test_string_groups_field_is_rejected_without_character_splitting(self):
        r = simulate_batch_schedule(
            [{"id": "A", "group_id": "A", "ammo": 1}],
            [{"groups": "A", "shots": {"A": 1}}],
        )
        self.assertFalse(r["schedule_valid"])
        self.assertEqual(
            r["batch_reports"][-1]["reason"],
            "GROUPS_MUST_BE_A_SEQUENCE",
        )
        self.assertEqual(r["conveyor_occupied"], 0)

    def test_string_reactivation_field_is_rejected_before_mutation(self):
        r = simulate_batch_schedule(
            [{"id": "A", "group_id": "A", "ammo": 0}],
            [
                {"groups": ["A"], "shots": {"A": 0}},
                {
                    "groups": ["A"],
                    "reactivate_groups": "A",
                    "shots": {"A": 0},
                },
            ],
            config=SimulatorConfig(conveyor_capacity=1, ticks_per_lap=1),
            allow_storage_reactivation=True,
        )
        self.assertFalse(r["schedule_valid"])
        self.assertEqual(
            r["batch_reports"][-1]["reason"],
            "REACTIVATE_GROUPS_MUST_BE_A_SEQUENCE",
        )
        self.assertEqual(r["returned_shooters"], ["A"])
        self.assertEqual(r["storage_occupied"], 1)

    def test_invalid_shot_count_is_rejected_before_group_selection(self):
        records = [{"id": "A", "group_id": "A", "ammo": 2}]
        r = simulate_batch_schedule(
            records,
            [{"groups": ["A"], "shots": {"A": 3}}],
            config=SimulatorConfig(conveyor_capacity=1, ticks_per_lap=3),
        )
        self.assertFalse(r["schedule_valid"])
        self.assertEqual(
            r["batch_reports"][-1]["reason"],
            "INVALID_OR_EXCESSIVE_SHOT_COUNT",
        )
        self.assertEqual(r["conveyor_occupied"], 0)
        self.assertEqual(r["tick_count"], 0)
        self.assertEqual(r["active_shooters"], [])

    def test_non_mapping_shot_input_is_rejected_before_reactivation(self):
        records = [{"id": "A", "group_id": "A", "ammo": 0}]
        r = simulate_batch_schedule(
            records,
            [
                {"groups": ["A"], "shots": {"A": 0}},
                {
                    "groups": ["A"],
                    "reactivate_groups": ["A"],
                    "shots": [],
                },
            ],
            config=SimulatorConfig(conveyor_capacity=1, ticks_per_lap=1),
            allow_storage_reactivation=True,
        )
        self.assertFalse(r["schedule_valid"])
        self.assertEqual(
            r["batch_reports"][-1]["reason"],
            "SHOTS_MUST_BE_A_MAPPING",
        )
        self.assertEqual(r["returned_shooters"], ["A"])
        self.assertEqual(r["storage_occupied"], 1)
        self.assertEqual(r["conveyor_occupied"], 0)

    def test_non_string_group_ids_are_rejected(self):
        cases = [
            ({"groups": [1]}, "GROUP_IDS_MUST_BE_NONEMPTY_STRINGS"),
            ({"groups": ["A"], "reactivate_groups": [1]},
             "REACTIVATION_GROUP_IDS_MUST_BE_NONEMPTY_STRINGS"),
            ({"groups": [""]}, "GROUP_IDS_MUST_BE_NONEMPTY_STRINGS"),
        ]
        for batch, reason in cases:
            with self.subTest(batch=batch):
                result = simulate_batch_schedule(
                    [{"id": "A", "group_id": "A", "ammo": 1}],
                    [batch],
                )
                self.assertFalse(result["schedule_valid"])
                self.assertEqual(result["batch_reports"][-1]["reason"], reason)
                self.assertEqual(result["conveyor_occupied"], 0)
                self.assertEqual(result["tick_count"], 0)

    def test_storage_reactivation_flag_must_be_boolean(self):
        result = simulate_batch_schedule(
            [{"id": "A", "group_id": "A", "ammo": 1}],
            [],
            allow_storage_reactivation="false",
        )
        self.assertFalse(result["schedule_valid"])
        self.assertEqual(
            result["failure_reason"],
            "ALLOW_STORAGE_REACTIVATION_MUST_BE_BOOLEAN",
        )

    def test_batch_iterator_interruption_preserves_completed_reports(self):
        def interrupted_batches():
            yield {"groups": ["A"], "shots": {"A": 1}}
            raise RuntimeError("input stream interrupted")

        result = simulate_batch_schedule(
            [{"id": "A", "group_id": "A", "ammo": 1}],
            interrupted_batches(),
            config=SimulatorConfig(
                conveyor_capacity=1, storage_capacity=2, ticks_per_lap=2
            ),
        )
        self.assertFalse(result["schedule_valid"])
        self.assertEqual(result["batches_completed"], 1)
        self.assertEqual(len(result["batch_reports"]), 2)
        self.assertTrue(result["batch_reports"][0]["valid"])
        self.assertEqual(result["batch_reports"][1]["batch"], 1)
        self.assertEqual(
            result["batch_reports"][1]["reason"],
            "BATCH_ITERATION_FAILED",
        )
        self.assertEqual(
            result["batch_reports"][1]["exception_type"],
            "RuntimeError",
        )
        self.assertEqual(result["groups_scheduled"], ["A"])
        self.assertFalse(result["live_execution_allowed"])
        self.assertFalse(result["gameplay_actions_performed"])

    def test_checkpoint_resume_matches_uninterrupted_schedule(self):
        records = [
            {"id": "A", "group_id": "A", "ammo": 1},
            {"id": "B", "group_id": "B", "ammo": 1},
        ]
        batches = [
            {"groups": ["A"], "shots": {"A": 1}},
            {"groups": ["B"], "shots": {"B": 1}},
        ]
        config = SimulatorConfig(
            conveyor_capacity=1, storage_capacity=3, ticks_per_lap=2
        )
        partial = simulate_batch_schedule(
            records, batches, config=config, max_batches=1
        )
        self.assertTrue(partial["schedule_valid"])
        self.assertFalse(partial["schedule_complete"])
        self.assertEqual(partial["next_batch_index"], 1)
        self.assertIsInstance(partial["checkpoint"], dict)
        self.assertEqual(partial["batches_completed"], 1)

        resumed = simulate_batch_schedule(
            records, batches, config=config,
            resume_from=partial["checkpoint"],
        )
        uninterrupted = simulate_batch_schedule(records, batches, config=config)
        self.assertTrue(resumed["schedule_valid"])
        self.assertTrue(resumed["schedule_complete"])
        self.assertIsNone(resumed["checkpoint"])
        self.assertEqual(resumed["batches_completed"], 2)
        for field in (
            "returned_shooters", "storage_occupied", "conveyor_occupied",
            "tick_count", "events", "groups_scheduled",
        ):
            self.assertEqual(resumed[field], uninterrupted[field], field)

    def test_checkpoint_rejects_changed_schedule(self):
        records = [{"id": "A", "group_id": "A", "ammo": 1}]
        batches = [
            {"groups": ["A"], "shots": {"A": 1}},
            {"groups": ["B"], "shots": {"B": 0}},
        ]
        partial = simulate_batch_schedule(
            records, batches, max_batches=1,
            config=SimulatorConfig(conveyor_capacity=2, ticks_per_lap=2),
        )
        changed = [
            {"groups": ["A"], "shots": {"A": 0}},
            {"groups": ["B"], "shots": {"B": 0}},
        ]
        resumed = simulate_batch_schedule(
            records, changed,
            config=SimulatorConfig(conveyor_capacity=2, ticks_per_lap=2),
            resume_from=partial["checkpoint"],
        )
        self.assertFalse(resumed["schedule_valid"])
        self.assertIn("INVALID_CHECKPOINT", resumed["failure_reason"])
        self.assertIn("does not match", resumed["failure_reason"])

    def test_checkpoint_rejects_boolean_schema_version(self):
        records = [{"id": "A", "group_id": "A", "ammo": 3}]
        batches = [
            {"groups": ["A"], "shots": {"A": 1}},
            {"groups": ["B"], "shots": {"B": 1}},
        ]
        partial = simulate_batch_schedule(
            records, batches, max_batches=1,
            config=SimulatorConfig(conveyor_capacity=2, ticks_per_lap=3),
        )
        checkpoint = partial["checkpoint"]
        self.assertIsInstance(checkpoint, dict)
        checkpoint["schema_version"] = True

        resumed = simulate_batch_schedule(
            records, batches,
            config=SimulatorConfig(conveyor_capacity=2, ticks_per_lap=3),
            resume_from=checkpoint,
        )
        self.assertFalse(resumed["schedule_valid"])
        self.assertIn("INVALID_CHECKPOINT", resumed["failure_reason"])
        self.assertIn("schema version", resumed["failure_reason"])

    def test_checkpoint_rejects_report_history_changed_from_original_batch(self):
        records = [{"id": "A", "group_id": "A", "ammo": 3},
                   {"id": "B", "group_id": "B", "ammo": 3}]
        batches = [
            {"groups": ["A"], "shots": {"A": 1}},
            {"groups": ["B"], "shots": {"B": 1}},
        ]
        partial = simulate_batch_schedule(
            records, batches, max_batches=1,
            config=SimulatorConfig(conveyor_capacity=3, ticks_per_lap=3),
        )
        checkpoint = partial["checkpoint"]
        self.assertIsInstance(checkpoint, dict)
        # The forged history claims A was reactivated even though the original
        # batch did not reactivate it. The seen set is adjusted to remain
        # internally self-consistent, so validation must compare to the schedule.
        checkpoint["batch_reports"][0]["reactivated_groups"] = ["A"]
        checkpoint["seen_groups"] = []

        resumed = simulate_batch_schedule(
            records, batches,
            config=SimulatorConfig(conveyor_capacity=3, ticks_per_lap=3),
            resume_from=checkpoint,
        )
        self.assertFalse(resumed["schedule_valid"])
        self.assertIn("INVALID_CHECKPOINT", resumed["failure_reason"])
        self.assertIn("original schedule", resumed["failure_reason"])

    def test_checkpoint_rejects_seen_group_missing_from_simulator_state(self):
        records = [{"id": "A", "group_id": "A", "ammo": 3}]
        batches = [
            {"groups": ["A"], "shots": {"A": 1}},
            {"groups": ["B"], "shots": {"B": 0}},
        ]
        partial = simulate_batch_schedule(
            records, batches, max_batches=1,
            config=SimulatorConfig(conveyor_capacity=2, ticks_per_lap=3),
        )
        checkpoint = partial["checkpoint"]
        self.assertIsInstance(checkpoint, dict)
        checkpoint["simulator_snapshot"]["shooters"][0]["selected"] = False

        resumed = simulate_batch_schedule(
            records, batches,
            config=SimulatorConfig(conveyor_capacity=2, ticks_per_lap=3),
            resume_from=checkpoint,
        )
        self.assertFalse(resumed["schedule_valid"])
        self.assertIn("INVALID_CHECKPOINT", resumed["failure_reason"])
        self.assertIn("not selected", resumed["failure_reason"])

    def test_checkpoint_mode_preserves_malformed_batch_rejection(self):
        result = simulate_batch_schedule(
            [{"id": "A", "group_id": "A", "ammo": 1}],
            [None],
            max_batches=1,
        )
        self.assertFalse(result["schedule_valid"])
        self.assertEqual(
            result["batch_reports"][-1]["reason"],
            "BATCH_MUST_BE_A_MAPPING",
        )
        self.assertIsNone(result["checkpoint"])

    def test_checkpoint_requires_finite_batch_sequence(self):
        result = simulate_batch_schedule(
            [{"id": "A", "group_id": "A", "ammo": 1}],
            iter([{"groups": ["A"], "shots": {"A": 1}}]),
            max_batches=1,
        )
        self.assertFalse(result["schedule_valid"])
        self.assertEqual(
            result["failure_reason"],
            "CHECKPOINT_REQUIRES_A_FINITE_BATCH_SEQUENCE",
        )

    def test_live_actions_disabled(self):
        r = simulate_batch_schedule(
            [{"id": "A", "group_id": "A", "ammo": 2}],
            [{"groups": ["A"], "shots": {"A": 1}}],
        )
        self.assertFalse(r["live_execution_allowed"])
        self.assertFalse(r["gameplay_actions_performed"])


    def test_malformed_shooter_record_inputs_fail_closed(self):
        cases = [
            (None, "SHOOTER_RECORDS_MUST_BE_A_SEQUENCE"),
            ([None], "SHOOTER_RECORD_MUST_BE_A_MAPPING"),
            ([{"ammo": 1}], "SHOOTER_ID_MUST_BE_A_NONEMPTY_STRING"),
            ([{"id": "A", "ammo": True}],
             "SHOOTER_AMMO_MUST_BE_A_NONNEGATIVE_INTEGER"),
            ([{"id": "A", "ammo": -1}],
             "SHOOTER_AMMO_MUST_BE_A_NONNEGATIVE_INTEGER"),
            ([{"id": "A", "ammo": 1, "position": 1.5}],
             "SHOOTER_POSITION_STATE_MUST_BE_NONNEGATIVE_INTEGER"),
            ([{"id": "A", "ammo": 1, "selected": "false"}],
             "SHOOTER_STATE_FLAGS_MUST_BE_BOOLEAN"),
            ([{"id": "A", "ammo": 1},
              {"id": "A", "ammo": 2}],
             "DUPLICATE_SHOOTER_ID"),
        ]
        for records, reason in cases:
            with self.subTest(records=records):
                result = simulate_batch_schedule(records, [])
                self.assertFalse(result["schedule_valid"])
                self.assertEqual(result["failure_reason"], reason)
                self.assertFalse(result["live_execution_allowed"])
                self.assertFalse(result["gameplay_actions_performed"])
                self.assertEqual(result["batches_completed"], 0)

    def test_malformed_initial_state_is_reported_without_exception(self):
        result = simulate_batch_schedule(
            [
                {"id": "A1", "group_id": "PAIR", "ammo": 1,
                 "selected": True},
                {"id": "A2", "group_id": "PAIR", "ammo": 1,
                 "selected": False},
            ],
            [],
            storage_occupied=0,
        )
        self.assertFalse(result["schedule_valid"])
        self.assertIn("INVALID_INITIAL_SIMULATOR_STATE", result["failure_reason"])


    def test_partial_group_selection_failure_rolls_back_entire_batch(self):
        from conveyor_simulator import ConveyorSimulator

        original = ConveyorSimulator.select_group
        calls = {"count": 0}

        def fail_second_group(sim, group_id):
            calls["count"] += 1
            if calls["count"] == 2:
                return False
            return original(sim, group_id)

        records = [
            {"id": "A", "group_id": "A", "ammo": 1},
            {"id": "B", "group_id": "B", "ammo": 1},
        ]
        with patch.object(
            ConveyorSimulator, "select_group", fail_second_group
        ):
            result = simulate_batch_schedule(
                records,
                [{"groups": ["A", "B"], "shots": {"A": 1, "B": 1}}],
                config=SimulatorConfig(conveyor_capacity=2, ticks_per_lap=3),
            )

        self.assertFalse(result["schedule_valid"])
        self.assertEqual(
            result["batch_reports"][-1]["reason"],
            "SIMULATOR_REJECTED_GROUP_SELECTION",
        )
        self.assertEqual(result["conveyor_occupied"], 0)
        self.assertEqual(result["active_shooters"], [])
        self.assertEqual(result["tick_count"], 0)
        self.assertEqual(result["returned_shooters"], [])

    def test_reactivation_is_rolled_back_if_later_selection_fails(self):
        from conveyor_simulator import ConveyorSimulator

        original = ConveyorSimulator.select_group
        calls = {"count": 0}

        def fail_second_group_in_third_batch(sim, group_id):
            calls["count"] += 1
            # The first two calls complete batches one and two. Fail
            # selecting the second group after batch three reactivates A.
            if calls["count"] == 4:
                return False
            return original(sim, group_id)

        records = [
            {"id": "A", "group_id": "A", "ammo": 0},
            {"id": "B", "group_id": "B", "ammo": 0},
            {"id": "C", "group_id": "C", "ammo": 1},
        ]
        batches = [
            {"groups": ["A"], "shots": {"A": 0}},
            {"groups": ["B"], "shots": {"B": 0}},
            {
                "groups": ["A", "C"],
                "reactivate_groups": ["A"],
                "shots": {"A": 0, "C": 0},
            },
        ]
        with patch.object(
            ConveyorSimulator, "select_group", fail_second_group_in_third_batch
        ):
            result = simulate_batch_schedule(
                records,
                batches,
                config=SimulatorConfig(
                    conveyor_capacity=3, storage_capacity=5, ticks_per_lap=1
                ),
                allow_storage_reactivation=True,
            )

        self.assertFalse(result["schedule_valid"])
        self.assertEqual(
            result["batch_reports"][-1]["reason"],
            "SIMULATOR_REJECTED_GROUP_SELECTION",
        )
        self.assertEqual(result["storage_occupied"], 2)
        self.assertEqual(set(result["returned_shooters"]), {"A", "B"})
        self.assertEqual(result["conveyor_occupied"], 0)
        self.assertEqual(result["active_shooters"], [])


    def test_storage_full_mid_tick_marks_batch_failed_and_preserves_partial_events(self):
        records = [
            {"id": "A", "group_id": "A", "ammo": 0},
            {"id": "B", "group_id": "B", "ammo": 0},
        ]
        result = simulate_batch_schedule(
            records,
            [{"groups": ["A", "B"], "shots": {"A": 0, "B": 0}}],
            storage_occupied=4,
            config=SimulatorConfig(
                conveyor_capacity=2, storage_capacity=5, ticks_per_lap=1
            ),
        )

        self.assertFalse(result["schedule_valid"])
        self.assertEqual(result["batches_completed"], 0)
        self.assertEqual(result["batch_reports"][0]["ticks_used"], 1)
        self.assertEqual(result["tick_count"], 1)
        self.assertFalse(result["batch_reports"][0]["valid"])
        self.assertTrue(result["batch_reports"][0]["failed"])
        self.assertIn("STORAGE_IS_FULL", result["batch_reports"][0]["reason"])
        self.assertEqual(result["storage_occupied"], 5)
        self.assertEqual(result["returned_shooters"], ["A"])
        self.assertEqual(
            [s["id"] for s in result["active_shooters"]], ["B"]
        )
        event_names = [event["event"] for event in result["events"]]
        self.assertIn("SHOOTER_RETURNED_TO_STORAGE", event_names)
        self.assertIn("LEVEL_FAILURE", event_names)


if __name__ == "__main__":
    unittest.main(verbosity=2)
