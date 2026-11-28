"""Unit tests for shooter_order_planner offline ordering logic.

These tests exercise pure functions with synthetic data only.
They do not load private Level 39 fixtures or enable any gameplay actions.
"""

import copy
import unittest

from shooter_order_planner import plan_orders, prepare_groups


def _shooter(shooter_id, colour="cyan", ammo=5, direction="top_down", lane=0, group_id=None):
    shooter = {
        "id": shooter_id,
        "direction": direction,
        "lane": lane,
        "colour": colour,
        "ammo": ammo,
    }
    if group_id is not None:
        shooter["group_id"] = group_id
    return shooter


class ShooterOrderPlannerTests(unittest.TestCase):
    def test_best_order_clears_all_targets(self):
        board = [["cyan"], ["white"], ["cyan"]]
        shooters = [
            _shooter("cyan_first", "cyan"),
            _shooter("white_middle", "white"),
            _shooter("cyan_last", "cyan"),
        ]

        plan = plan_orders(board, shooters)

        self.assertEqual(plan["best_result"]["remaining_pixels"], 0)
        self.assertEqual(plan["best_result"]["total_pixels_removed"], 3)
        self.assertEqual(plan["orders_evaluated"], 6)

    def test_bonded_shooters_remain_together_and_preserve_order(self):
        bonded = [
            _shooter("bond_a", "cyan", ammo=2, direction="top_down", lane=0, group_id="bonded_pair"),
            _shooter("bond_b", "white", ammo=2, direction="bottom_up", lane=1, group_id="bonded_pair"),
            _shooter("single_c", "cyan", ammo=2, direction="left_right", lane=0),
        ]
        board = [["cyan", "white"], ["cyan", "white"]]

        plan = plan_orders(board, bonded)
        best_order = plan["best_shooter_order"]
        positions = [best_order.index("bond_a"), best_order.index("bond_b")]

        self.assertEqual(positions[1], positions[0] + 1)
        self.assertEqual(positions, sorted(positions))

    def test_single_bonded_group_is_one_ordering_unit(self):
        bonded = [
            _shooter("bond_a", "cyan", ammo=2, group_id="bonded_pair"),
            _shooter("bond_b", "white", ammo=2, group_id="bonded_pair"),
        ]
        plan = plan_orders([["cyan", "white"]], bonded)

        self.assertEqual(plan["groups_searched"], 1)
        self.assertEqual(plan["orders_evaluated"], 1)

    def test_conveyor_capacity_enforced(self):
        shooters = [_shooter(f"s{i}", ammo=1) for i in range(6)]
        with self.assertRaises(ValueError):
            plan_orders([["cyan"]] * 6, shooters)

    def test_duplicate_ids_rejected(self):
        shooters = [
            _shooter("duplicate"),
            _shooter("duplicate"),
        ]
        with self.assertRaises(ValueError):
            plan_orders([["cyan"]], shooters)

    def test_source_board_remains_unchanged(self):
        board = [["cyan"], ["white"], ["cyan"]]
        original = copy.deepcopy(board)
        shooters = [
            _shooter("cyan_first", "cyan"),
            _shooter("white_middle", "white"),
            _shooter("cyan_last", "cyan"),
        ]

        plan_orders(board, shooters)
        self.assertEqual(board, original)

    def test_prepare_groups_rejects_empty_list(self):
        with self.assertRaises(ValueError):
            prepare_groups([])

    def test_prepare_groups_rejects_non_list(self):
        with self.assertRaises(ValueError):
            prepare_groups(None)

    def test_prepare_groups_rejects_invalid_capacity(self):
        shooter = _shooter("s1")
        for bad in (0, -1, True, 1.5, "5"):
            with self.assertRaises(ValueError):
                prepare_groups([shooter], conveyor_capacity=bad)

    def test_prepare_groups_rejects_empty_group_id(self):
        shooter = _shooter("s1", group_id="   ")
        with self.assertRaises(ValueError):
            prepare_groups([shooter])

    def test_prepare_groups_rejects_non_string_group_id(self):
        shooter = _shooter("s1")
        shooter["group_id"] = 123
        with self.assertRaises(ValueError):
            prepare_groups([shooter])

    def test_prepare_groups_rejects_empty_shooter_id(self):
        shooter = _shooter("   ")
        with self.assertRaises(ValueError):
            prepare_groups([shooter])


if __name__ == "__main__":
    unittest.main()
