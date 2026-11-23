"""Unified advisory decision output for ordinary moves and power-ups.

This is a read-only composition layer. It delegates ordinary move eligibility
to the evidence-gated planner and power-up scoring to the advisory evaluator.
It never changes the state, inventory, or device.
"""
from planner import plan_next_move
from powerup_planner import evaluate_powerup_candidates, score_powerup_candidates


def plan_next_decision(
    state,
    *,
    planning_report=None,
    identity_audit=None,
    candidate_report=None,
    snapshot_report=None,
    powerup_inventory=None,
    hidden_board_circles=None,
    observed_extra_slots=None,
):
    ordinary_move = plan_next_move(
        state,
        planning_report=planning_report,
        identity_audit=identity_audit,
        candidate_report=candidate_report,
        snapshot_report=snapshot_report,
    )
    powerup_result = None
    if powerup_inventory is not None:
        powerup_result = evaluate_powerup_candidates(
            state,
            powerup_inventory,
            hidden_board_circles=hidden_board_circles,
            observed_extra_slots=observed_extra_slots,
        )
        if powerup_result.get("eligible") is True:
            powerup_result["strategic_ranking"] = score_powerup_candidates(
                state, powerup_inventory, powerup_result
            )
    return {
        "ordinary_move": ordinary_move,
        "ordinary_move_evidence_gated": True,
        "powerup_advice": powerup_result,
        "gameplay_verified": False,
        "game_taps_enabled": False,
        "actions_performed": False,
    }
