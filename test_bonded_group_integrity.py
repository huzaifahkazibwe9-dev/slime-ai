import unittest

from game_state import GameState, Shooter


class BondedGroupIntegrityTests(unittest.TestCase):
    def test_three_shooter_chain_is_one_atomic_group(self):
        a = Shooter("A", "red", 1, accessible=True, bonded_ids=["B"])
        b = Shooter("B", "blue", 1, bonded_ids=["A", "C"])
        c = Shooter("C", "green", 1, bonded_ids=["B"])
        state = GameState(board=[["red"]], shooters={"A": a, "B": b, "C": c})
        self.assertEqual(state.bonded_group("A"), ["A", "B", "C"])
        self.assertTrue(state.can_select_group("A"))
        self.assertTrue(state.select_group("A"))
        self.assertEqual(state.conveyor, ["A", "B", "C"])

    def test_bonded_component_is_independent_of_selected_member(self):
        a = Shooter("A", "red", 1, bonded_ids=["B"])
        b = Shooter("B", "blue", 1, bonded_ids=["A", "C"])
        c = Shooter("C", "green", 1, bonded_ids=["B"])
        state = GameState(board=[["red"]], shooters={"A": a, "B": b, "C": c})
        self.assertEqual(state.bonded_group("A"), state.bonded_group("C"))

    def test_component_larger_than_three_is_not_selectable(self):
        shooters = {
            name: Shooter(name, "red", 1, accessible=(name == "A"),
                          bonded_ids=[other for other in "ABCD" if other != name])
            for name in "ABCD"
        }
        state = GameState(board=[["red"]], shooters=shooters)
        self.assertEqual(state.bonded_group("A"), [])
        self.assertFalse(state.can_select_group("A"))

    def test_unknown_bonded_member_invalidates_component(self):
        state = GameState(
            board=[["red"]],
            shooters={"A": Shooter("A", "red", 1, accessible=True,
                                   bonded_ids=["MISSING"])},
        )
        self.assertEqual(state.bonded_group("A"), [])
        self.assertTrue(any("Unknown bonded shooter" in e for e in state.validate()))


if __name__ == "__main__":
    unittest.main(verbosity=2)
