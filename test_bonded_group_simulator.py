import unittest

from game_state import GameState, Shooter
from bonded_group_simulator import simulate_bonded_group


class BondedGroupSimulatorTests(unittest.TestCase):
    def make_state(self, limited=False):
        a = Shooter("A", "red", 2, "right", -1, 0, accessible=True)
        b = Shooter("B", "red", 2, "right", -1, 1, accessible=True)
        a.bonded_ids = ["B"]
        b.bonded_ids = ["A"]

        shooters = {"A": a, "B": b}
        conveyor = []

        if limited:
            for i in range(4):
                sid = f"X{i}"
                shooters[sid] = Shooter(
                    sid, "blue", 1, "right", -1, 0, accessible=False
                )
                conveyor.append(sid)

        return GameState(
            board=[["red", "blue"], ["red", "red"]],
            shooters=shooters,
            conveyor=conveyor,
        )

    def test_bonded_group_selected_atomically(self):
        state = self.make_state()
        report = simulate_bonded_group(state, "A")
        self.assertEqual(report["status"], "SIMULATED")
        self.assertEqual(report["shooter_ids"], ["A", "B"])
        self.assertTrue(report["group_selected_atomically"])
        self.assertIn("A", report["conveyor_after_selection"])
        self.assertIn("B", report["conveyor_after_selection"])

    def test_group_fires_and_updates_private_board(self):
        report = simulate_bonded_group(self.make_state(), "A")
        self.assertEqual(report["pixels_removed"], 3)
        self.assertEqual(report["remaining_pixels"], 1)
        self.assertEqual(report["final_region_graph"]["occupied_cells"], 1)

    def test_group_capacity_is_enforced(self):
        report = simulate_bonded_group(self.make_state(limited=True), "A")
        self.assertEqual(report["status"], "GROUP_NOT_SELECTABLE")
        self.assertFalse(report["live_execution_allowed"])

    def test_source_state_is_unchanged(self):
        state = self.make_state()
        before_board = [row[:] for row in state.board]
        before_conveyor = list(state.conveyor)
        before_ammo = {k: v.ammo for k, v in state.shooters.items()}

        report = simulate_bonded_group(state, "A")

        self.assertEqual(state.board, before_board)
        self.assertEqual(state.conveyor, before_conveyor)
        self.assertEqual(
            {k: v.ammo for k, v in state.shooters.items()},
            before_ammo,
        )
        self.assertTrue(report["source_state_unchanged"])

    def test_consume_state_uses_disposable_state_without_changing_default_contract(self):
        disposable = self.make_state()
        original = self.make_state()
        report = simulate_bonded_group(disposable, "A", consume_state=True)
        self.assertEqual(report["status"], "SIMULATED")
        self.assertEqual(original.board, [["red", "blue"], ["red", "red"]])
        self.assertEqual(disposable.board, report["final_board"])
        self.assertEqual(disposable.shooters["A"].ammo, report["remaining_ammo"]["A"])
        self.assertFalse(report["source_state_unchanged"])
        self.assertFalse(report["source_state_integrity_checked"])

    def test_final_board_isolated_from_source_in_default_mode(self):
        state = self.make_state()
        report = simulate_bonded_group(state, "A")
        self.assertIsNot(report["final_board"], state.board)
        self.assertEqual(state.board, [["red", "blue"], ["red", "red"]])

    def test_consume_state_returns_disposable_board_without_another_copy(self):
        disposable = self.make_state()
        report = simulate_bonded_group(disposable, "A", consume_state=True)
        self.assertIs(report["final_board"], disposable.board)

    def test_consume_state_requires_boolean(self):
        with self.assertRaises(TypeError):
            simulate_bonded_group(self.make_state(), "A", consume_state=1)

    def test_unknown_shooter_rejected(self):
        with self.assertRaises(ValueError):
            simulate_bonded_group(self.make_state(), "UNKNOWN")

    def test_live_execution_remains_disabled(self):
        report = simulate_bonded_group(self.make_state(), "A")
        self.assertFalse(report["gameplay_verified"])
        self.assertFalse(report["evidence_verified"])
        self.assertFalse(report["live_execution_allowed"])
        self.assertFalse(report["game_taps_enabled"])


if __name__ == "__main__":
    unittest.main()
