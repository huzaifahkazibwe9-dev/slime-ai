import copy
import unittest

from execution_engine import (
    run_dry_simulation, _simulate_conveyor_batch, run_multi_batch_schedule
)
from game_state import GameState, Shooter


class ExecutionEngineTests(unittest.TestCase):

    def make_state(self, board, shooters, conveyor=None):
        return GameState(
            board=board,
            shooters={item.id: item for item in shooters},
            conveyor=conveyor or [],
        )

    def test_matching_pixels_removed(self):
        state = self.make_state([["red", "red"]], [
            Shooter("R", "red", 3, "right", -1, 0, accessible=True)
        ])
        report = run_dry_simulation(state)
        self.assertEqual(report["best"]["pixels_removed"], 2)
        self.assertEqual(report["best"]["remaining_pixels"], 0)

    def test_source_state_unchanged(self):
        state = self.make_state([["red", "red"]], [
            Shooter("R", "red", 3, "right", -1, 0, accessible=True)
        ])
        before = copy.deepcopy(state)
        report = run_dry_simulation(state)
        self.assertTrue(report["source_state_unchanged"])
        self.assertEqual(state.board, before.board)
        self.assertEqual(state.shooters["R"].ammo, before.shooters["R"].ammo)

    def test_different_colour_blocks_shot(self):
        state = self.make_state([["blue", "red"]], [
            Shooter("R", "red", 3, "right", -1, 0, accessible=True)
        ])
        report = run_dry_simulation(state)
        self.assertEqual(report["best"]["pixels_removed"], 0)
        self.assertGreater(report["best"]["blocked_attempts"], 0)

    def test_bonded_group_selected_together(self):
        a = Shooter(
            "A", "red", 2, "right", -1, 0,
            accessible=True, group_id="pair", bonded_ids=["B"]
        )
        b = Shooter(
            "B", "blue", 2, "left", 2, 0,
            accessible=False, group_id="pair", bonded_ids=["A"]
        )
        state = self.make_state([["red", None, "blue"]], [a, b])
        report = run_dry_simulation(state)
        self.assertEqual(report["best"]["groups"], [["A", "B"]])
        self.assertEqual(report["best"]["conveyor_used"], 2)

    def test_game_state_rejects_unsubstantiated_visual_verification_flags(self):
        shooter = Shooter(
            "A", "red", 2, "right", -1, 0,
            accessible=True,
            observation_quality={
                "colour_independently_verified": True,
                "ammunition_independently_verified": False,
                "slot_mapping_independently_verified": False,
            },
        )
        self.assertFalse(shooter.valid())

    def test_malformed_bond_metadata_fails_closed_without_raising(self):
        for malformed in (None, "B", [["B"]], [None], [1]):
            with self.subTest(bonded_ids=malformed):
                shooter = Shooter(
                    "A", "red", 2, "right", -1, 0,
                    accessible=True, bonded_ids=malformed,
                )
                state = self.make_state([["red"]], [shooter])
                self.assertFalse(shooter.valid())
                self.assertEqual(state.bonded_group("A"), [])
                self.assertFalse(state.can_select_group("A"))
                self.assertTrue(state.validate())

    def test_asymmetric_bond_observation_cannot_be_selected(self):
        a = Shooter(
            "A", "red", 2, "right", -1, 0,
            accessible=True, bonded_ids=["B"],
        )
        b = Shooter(
            "B", "blue", 2, "left", 2, 0,
            bonded_ids=[],
        )
        state = self.make_state([["red", None, "blue"]], [a, b])
        self.assertFalse(state.can_select_group("A"))
        self.assertFalse(state.select_group("A"))
        self.assertEqual(state.conveyor, [])
        self.assertTrue(any("Asymmetric bond" in error for error in state.validate()))

    def test_conflicting_bond_group_ids_cannot_be_selected(self):
        a = Shooter(
            "A", "red", 2, "right", -1, 0,
            accessible=True, group_id="pair-a", bonded_ids=["B"],
        )
        b = Shooter(
            "B", "blue", 2, "left", 2, 0,
            group_id="pair-b", bonded_ids=["A"],
        )
        state = self.make_state([["red", None, "blue"]], [a, b])
        self.assertIsNone(state.bonded_group_id("A"))
        self.assertFalse(state.can_select_group("A"))
        self.assertFalse(state.select_group("A"))
        self.assertEqual(state.conveyor, [])
        self.assertTrue(any("Inconsistent group_id" in error for error in state.validate()))

    def test_validation_reports_bonded_component_over_three(self):
        shooters = [
            Shooter("A", "red", 2, "right", -1, 0,
                    accessible=True, bonded_ids=["B"]),
            Shooter("B", "blue", 2, "left", 2, 0,
                    bonded_ids=["A", "C"]),
            Shooter("C", "green", 2, "up", 0, -1,
                    bonded_ids=["B", "D"]),
            Shooter("D", "yellow", 2, "down", 0, 2,
                    bonded_ids=["C"]),
        ]
        state = self.make_state([["red"]], shooters)
        errors = state.validate()
        self.assertTrue(any(
            "Bonded group exceeds maximum size of 3" in error
            for error in errors
        ))
        self.assertFalse(state.can_select_group("A"))

    def test_non_string_group_id_fails_closed(self):
        shooter = Shooter(
            "A", "red", 2, "right", -1, 0,
            accessible=True, group_id=["not", "a", "string"],
        )
        state = self.make_state([["red"]], [shooter])
        self.assertFalse(shooter.valid())
        self.assertFalse(state.can_select_group("A"))
        self.assertTrue(any(
            "Invalid shooter: A" in error for error in state.validate()
        ))

    def test_conveyor_dry_run_uses_canonical_explicit_group_id(self):
        a = Shooter(
            "A", "red", 2, "right", -1, 0,
            accessible=True, group_id="pair-42", bonded_ids=["B"]
        )
        b = Shooter(
            "B", "blue", 2, "left", 2, 0,
            accessible=False, group_id="pair-42", bonded_ids=["A"]
        )
        original = self.make_state([["red", None, "blue"]], [a, b])
        simulated = copy.deepcopy(original)
        self.assertTrue(simulated.select_group("A"))
        report = _simulate_conveyor_batch(original, simulated, [("A", "B")])
        self.assertTrue(report["batch_selection_valid"])
        self.assertFalse(report["failed"])
        active = report["active_shooters"]
        self.assertEqual(len(active), 2)
        self.assertEqual({item["group_id"] for item in active}, {"pair-42"})

    def test_existing_conveyor_partial_bonded_group_is_rejected(self):
        a = Shooter(
            "A", "red", 2, "right", -1, 0,
            group_id="pair", bonded_ids=["B"]
        )
        b = Shooter(
            "B", "blue", 2, "left", 2, 0,
            group_id="pair", bonded_ids=["A"]
        )
        original = self.make_state(
            [["red", None, "blue"]], [a, b], conveyor=["A"]
        )
        simulated = copy.deepcopy(original)
        report = _simulate_conveyor_batch(original, simulated, [])
        self.assertFalse(report["batch_selection_valid"])
        self.assertEqual(
            report["failure_reason"], "PARTIAL_BONDED_GROUP_ON_CONVEYOR"
        )

    def test_unsynchronized_bonded_conveyor_positions_fail_closed(self):
        a = Shooter(
            "A", "red", 2, "right", -1, 0,
            group_id="pair", bonded_ids=["B"], rotation_progress=0.1
        )
        b = Shooter(
            "B", "blue", 2, "left", 2, 0,
            group_id="pair", bonded_ids=["A"], rotation_progress=0.4
        )
        original = self.make_state(
            [["red", None, "blue"]], [a, b], conveyor=["A", "B"]
        )
        simulated = copy.deepcopy(original)

        report = _simulate_conveyor_batch(original, simulated, [])

        self.assertFalse(report["batch_selection_valid"])
        self.assertEqual(
            report["failure_reason"],
            "UNSYNCHRONIZED_BONDED_GROUP_ON_CONVEYOR",
        )
        self.assertEqual(report["group_id"], "pair")
        self.assertEqual(report["abstract_positions"], [0, 2])

    def test_unknown_ammo_on_existing_conveyor_is_rejected(self):
        hidden = Shooter(
            "H", None, None, "right", -1, 0, revealed=False
        )
        original = self.make_state([[None]], [hidden], conveyor=["H"])
        simulated = copy.deepcopy(original)
        report = _simulate_conveyor_batch(original, simulated, [])
        self.assertFalse(report["batch_selection_valid"])
        self.assertEqual(
            report["failure_reason"], "UNKNOWN_AMMO_ON_EXISTING_CONVEYOR"
        )

    def test_candidate_conveyor_simulation_rejects_unknown_ammo(self):
        hidden = Shooter(
            "H", None, None, "right", -1, 0, revealed=False
        )
        original = self.make_state([[None]], [hidden])
        simulated = copy.deepcopy(original)

        report = _simulate_conveyor_batch(
            original, simulated, [("H",)]
        )

        self.assertFalse(report["batch_selection_valid"])
        self.assertEqual(
            report["failure_reason"],
            "UNKNOWN_OR_INVALID_AMMO_ON_CANDIDATE_SHOOTER",
        )
        self.assertEqual(report["shooter_id"], "H")
        self.assertEqual(original.shooters["H"].ammo, None)
        self.assertEqual(simulated.shooters["H"].ammo, None)

    def test_multi_batch_adapter_rejects_invalid_config_without_exception(self):
        state = self.make_state([["red"]], [
            Shooter("R", "red", 2, "right", -1, 0, accessible=True)
        ])
        before = copy.deepcopy(state)

        report = run_multi_batch_schedule(state, [], config=False)

        self.assertFalse(report["schedule_valid"])
        self.assertEqual(
            report["failure_reason"],
            "CONFIG_MUST_BE_SIMULATOR_CONFIG",
        )
        self.assertTrue(report["source_state_unchanged"])
        self.assertEqual(state.board, before.board)
        self.assertEqual(state.shooters["R"].ammo, before.shooters["R"].ammo)
        self.assertFalse(report["gameplay_actions_performed"])

    def test_multi_batch_adapter_rejects_unknown_ammo_instead_of_assuming_zero(self):
        visible = Shooter("V", "red", 2, "right", -1, 0, accessible=True)
        hidden = Shooter(
            "H", None, None, "right", -1, 0, revealed=False
        )
        cases = [
            ([hidden], [{"groups": ["H"], "shots": {"H": 0}}]),
            ([visible, hidden], [{"groups": ["V"], "shots": {"V": 1}}]),
        ]
        for shooters, batches in cases:
            with self.subTest(shooters=[item.id for item in shooters]):
                state = self.make_state([[None]], shooters)
                report = run_multi_batch_schedule(state, batches)
                self.assertFalse(report["schedule_valid"])
                self.assertIn(
                    "SHOOTER_AMMO_MUST_BE_A_NONNEGATIVE_INTEGER",
                    report["failure_reason"],
                )
                self.assertTrue(report["source_state_unchanged"])
                self.assertFalse(report["gameplay_actions_performed"])

    def test_three_bond_group_rejected_with_one_slot(self):
        shooters = [
            Shooter("A", "red", 1, "right", -1, 0,
                    accessible=True, bonded_ids=["B", "C"]),
            Shooter("B", "red", 1, "right", -1, 0,
                    bonded_ids=["A", "C"]),
            Shooter("C", "red", 1, "right", -1, 0,
                    bonded_ids=["A", "B"]),
        ]
        fillers = [
            Shooter(key, "blue", 1, "left", 1, 0)
            for key in ("D", "E", "F", "G")
        ]
        state = self.make_state(
            [["red"]], shooters + fillers,
            conveyor=["D", "E", "F", "G"]
        )
        report = run_dry_simulation(state)
        self.assertEqual(report["status"], "NO_LEGAL_BATCH")

    def test_live_execution_is_always_disabled(self):
        state = self.make_state([["red"]], [
            Shooter("R", "red", 1, "right", -1, 0, accessible=True)
        ])
        report = run_dry_simulation(state)
        self.assertFalse(report["live_execution_allowed"])
        self.assertFalse(report["gameplay_actions_performed"])

    def test_candidate_limit(self):
        shooters = [
            Shooter(str(i), "red", 1, "right", -1, 0, accessible=True)
            for i in range(4)
        ]
        state = self.make_state([["red"]], shooters)
        report = run_dry_simulation(state, max_candidates=3)
        self.assertLessEqual(report["candidates_examined"], 3)
        self.assertTrue(report["search_truncated"])


if __name__ == "__main__":
    unittest.main(verbosity=2)


class ConveyorGeometryIntegrationTests(unittest.TestCase):
    def calculate(self, **overrides):
        from conveyor_geometry import calculate_firing_geometry
        values = {
            "screen_center": (540, 1200),
            "segment": "bottom",
            "image_size": (1080, 2220),
            "position_verified": True,
        }
        values.update(overrides)
        return calculate_firing_geometry(**values)

    def test_valid_geometry_maps_without_enabling_live_taps(self):
        result = self.calculate()
        self.assertEqual(result["direction"], "up")
        self.assertFalse(result["game_taps_enabled"])

    def test_rejects_malformed_numeric_geometry_inputs(self):
        cases = (
            {"screen_center": None},
            {"screen_center": (540, float("nan"))},
            {"screen_center": (540, float("inf"))},
            {"screen_center": (True, 1200)},
            {"image_size": (1080, True)},
            {"image_size": (1080, 0)},
            {"board_bounds": (1, 2, 1, 4)},
            {"board_bounds": (1, 2, 3, float("nan"))},
            {"grid_size": (35, True)},
            {"grid_size": (35.0, 35)},
        )
        for overrides in cases:
            with self.subTest(overrides=overrides):
                with self.assertRaises(ValueError):
                    self.calculate(**overrides)

    def test_rejects_centres_outside_declared_conveyor_segment(self):
        cases = (
            ("bottom", (200, 1200)),
            ("top", (200, 400)),
            ("right", (900, 430)),
            ("right", (900, 1114)),
            ("left", (180, 430)),
            ("left", (180, 1114)),
        )
        for segment, center in cases:
            with self.subTest(segment=segment, center=center):
                with self.assertRaises(ValueError):
                    self.calculate(segment=segment, screen_center=center)

    def test_accepts_all_four_declared_conveyor_segments(self):
        cases = (
            ("bottom", (540, 1200)),
            ("top", (540, 400)),
            ("right", (900, 700)),
            ("left", (180, 700)),
        )
        for segment, center in cases:
            with self.subTest(segment=segment):
                result = self.calculate(segment=segment, screen_center=center)
                self.assertTrue(result["verified_screen_position"])
                self.assertFalse(result["game_taps_enabled"])

    def test_geometry_adapter_requires_explicit_position_confirmation(self):
        from geometry_adapter import apply_geometry
        shooter = Shooter("S1", "cyan", 20, accessible=True)
        before = (shooter.x, shooter.y, shooter.direction, shooter.accessible)
        with self.assertRaisesRegex(ValueError, "explicitly verified"):
            apply_geometry(
                shooter, (540, 1200), "bottom", (1080, 2220),
                position_verified=False,
            )
        self.assertEqual(
            (shooter.x, shooter.y, shooter.direction, shooter.accessible),
            before,
        )

    def test_geometry_adapter_rejects_invalid_geometry_without_mutation(self):
        from geometry_adapter import apply_geometry
        shooter = Shooter("S1", "cyan", 20, accessible=True)
        before = (
            shooter.x, shooter.y, shooter.direction,
            shooter.screen_center, shooter.screen_center_verified,
            shooter.accessible,
        )
        with self.assertRaises(ValueError):
            apply_geometry(
                shooter, (540, 1200), "diagonal", (1080, 2220),
                position_verified=True,
            )
        self.assertEqual(
            (
                shooter.x, shooter.y, shooter.direction,
                shooter.screen_center, shooter.screen_center_verified,
                shooter.accessible,
            ),
            before,
        )
