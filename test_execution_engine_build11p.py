import unittest

from game_state import GameState, Shooter
from execution_engine import run_dry_simulation


class Build11PIntegrationTests(unittest.TestCase):

    def make_state(self, existing_count=4):
        shooters = {}
        conveyor = []

        for index in range(existing_count):
            shooter_id = f"E{index}"
            shooters[shooter_id] = Shooter(
                shooter_id, "blue", 10, "left", 0, 0,
                group_id=shooter_id,
                rotation_progress=0.4,
            )
            conveyor.append(shooter_id)

        shooters["R"] = Shooter(
            "R", "red", 1, "right", -1, 0,
            accessible=True,
        )

        return GameState(
            board=[["red"]],
            shooters=shooters,
            conveyor=conveyor,
            storage=[],
        )

    def test_existing_conveyor_occupants_are_restored(self):
        state = self.make_state(existing_count=4)
        report = run_dry_simulation(state)
        candidate = report["best"]

        self.assertIsNotNone(candidate)
        simulation = candidate["conveyor_simulation"]

        self.assertTrue(simulation["existing_conveyor_state_restored"])
        self.assertEqual(
            simulation["existing_conveyor_shooters"],
            ["E0", "E1", "E2", "E3"],
        )

        active_ids = {
            item["id"] for item in simulation["active_shooters"]
        }
        self.assertEqual(active_ids, {"E0", "E1", "E2", "E3"})
        self.assertEqual(simulation["conveyor_occupied"], 4)
        self.assertFalse(
            simulation["rotation_progress_mapping_calibrated"]
        )

    def test_full_existing_conveyor_prevents_new_selection(self):
        state = self.make_state(existing_count=5)
        report = run_dry_simulation(state)

        self.assertIsNone(report["best"])
        self.assertEqual(report["accessible_group_count"], 0)
        self.assertEqual(report["status"], "NO_LEGAL_BATCH")

    def test_existing_conveyor_ammunition_is_preserved(self):
        state = self.make_state(existing_count=1)
        report = run_dry_simulation(state)
        simulation = report["best"]["conveyor_simulation"]

        existing = next(
            item for item in simulation["active_shooters"]
            if item["id"] == "E0"
        )
        self.assertEqual(existing["ammo"], 10)
        self.assertEqual(existing["completed_laps"], 1)

    def test_live_actions_remain_disabled(self):
        report = run_dry_simulation(self.make_state())
        candidate = report["best"]

        self.assertFalse(report["live_execution_allowed"])
        self.assertFalse(report["gameplay_actions_performed"])
        self.assertFalse(
            candidate["conveyor_simulation"]["live_actions_performed"]
        )
        self.assertFalse(
            candidate["conveyor_simulation"]["live_taps_enabled"]
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
