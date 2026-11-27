import copy
import unittest

from game_state import GameState, Shooter


class GameStateStorageTransitionTests(unittest.TestCase):
    def make_state(self, storage, conveyor):
        shooters = {
            "A1": Shooter(
                "A1", "red", 3, accessible=False, group_id="PAIR",
                rotation_progress=0.4, bonded_ids=["A2"],
            ),
            "A2": Shooter(
                "A2", "blue", 2, accessible=False, group_id="PAIR",
                rotation_progress=0.7, bonded_ids=["A1"],
            ),
        }
        for shooter_id in set(storage + conveyor) - set(shooters):
            shooters[shooter_id] = Shooter(
                shooter_id, "green", 1, accessible=False,
            )
        return GameState(
            board=[["red"]],
            shooters=shooters,
            conveyor=list(conveyor),
            storage=list(storage),
        )

    def test_complete_bonded_group_returns_atomically_at_exact_capacity(self):
        state = self.make_state(
            storage=["A1", "A2"],
            conveyor=["C1", "C2", "C3"],
        )
        self.assertEqual(state.validate(), [])
        self.assertTrue(state.can_return_from_storage("A1"))
        self.assertTrue(state.transfer_from_storage("A1"))
        self.assertEqual(state.storage, [])
        self.assertEqual(state.conveyor, ["C1", "C2", "C3", "A1", "A2"])
        self.assertEqual(
            [state.shooters[item].rotation_progress for item in ("A1", "A2")],
            [0.0, 0.0],
        )

    def test_bonded_group_is_rejected_when_only_one_conveyor_slot_is_free(self):
        state = self.make_state(
            storage=["A1", "A2"],
            conveyor=["C1", "C2", "C3", "C4"],
        )
        before = copy.deepcopy(state)
        self.assertFalse(state.can_return_from_storage("A1"))
        self.assertFalse(state.transfer_from_storage("A1"))
        self.assertEqual(state, before)

    def test_partial_bonded_group_in_storage_cannot_be_transferred(self):
        state = self.make_state(storage=["A1"], conveyor=[])
        before = copy.deepcopy(state)
        self.assertFalse(state.can_return_from_storage("A1"))
        self.assertFalse(state.transfer_from_storage("A1"))
        self.assertEqual(state, before)

    def test_bonded_group_split_between_storage_and_conveyor_cannot_transfer(self):
        state = self.make_state(storage=["A2"], conveyor=["A1"])
        before = copy.deepcopy(state)
        self.assertFalse(state.can_return_from_storage("A1"))
        self.assertFalse(state.transfer_from_storage("A1"))
        self.assertEqual(state, before)

    def test_duplicate_storage_occupancy_is_rejected_without_mutation(self):
        state = self.make_state(storage=["A1", "A1", "A2"], conveyor=[])
        before = copy.deepcopy(state)
        self.assertFalse(state.can_return_from_storage("A1"))
        self.assertFalse(state.transfer_from_storage("A1"))
        self.assertEqual(state, before)

    def test_unbonded_single_shooter_can_still_return_from_storage(self):
        state = self.make_state(storage=["S"], conveyor=["C1", "C2", "C3", "C4"])
        state.shooters["S"] = Shooter(
            "S", "yellow", 1, accessible=False,
            rotation_progress=0.6,
        )
        self.assertTrue(state.can_return_from_storage("S"))
        self.assertTrue(state.transfer_from_storage("S"))
        self.assertEqual(state.storage, [])
        self.assertEqual(state.conveyor, ["C1", "C2", "C3", "C4", "S"])
        self.assertEqual(state.shooters["S"].rotation_progress, 0.0)

    def test_malformed_shooter_identifier_is_rejected(self):
        state = self.make_state(storage=["A1", "A2"], conveyor=[])
        before = copy.deepcopy(state)
        self.assertFalse(state.can_return_from_storage(["A1"]))
        self.assertFalse(state.transfer_from_storage(["A1"]))
        self.assertEqual(state, before)


if __name__ == "__main__":
    unittest.main()
