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


if __name__ == "__main__":
    unittest.main(verbosity=2)
