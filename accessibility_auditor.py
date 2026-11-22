"""Build11AG: evidence-based shooter accessibility audit."""

from execution_engine import available_groups


def audit_accessibility(state, observations=None):
    observations = observations or {}
    results = []
    seen = set()

    for shooter_id, shooter in state.shooters.items():
        group = state.bonded_group(shooter_id)
        group_key = tuple(sorted(group)) if group else ()

        if group_key and group_key in seen:
            continue
        if group_key:
            seen.add(group_key)

        members = group or [shooter_id]
        reasons = []

        if not group:
            reasons.append("INVALID_OR_INCOMPLETE_BONDED_GROUP")

        if any(member not in state.shooters for member in members):
            reasons.append("UNKNOWN_GROUP_MEMBER")
            group_shooters = []
        else:
            group_shooters = [
                state.shooters[member] for member in members
            ]

        if any(item.panel_center is None for item in group_shooters):
            reasons.append("PANEL_POSITION_MISSING")

        if any(not item.accessible for item in group_shooters):
            reasons.append("ACCESSIBILITY_NOT_ESTABLISHED")

        if any(
            member in state.conveyor or member in state.storage
            for member in members
        ):
            reasons.append("GROUP_ALREADY_IN_CONVEYOR_OR_STORAGE")

        if len(members) > state.conveyor_free:
            reasons.append("INSUFFICIENT_CONVEYOR_CAPACITY")

        observation = observations.get("|".join(sorted(members)), {})
        if observation.get("tappable") is not True:
            reasons.append("NO_VERIFIED_TAPPABILITY_OBSERVATION")

        results.append({
            "group": members,
            "group_id": shooter.group_id,
            "eligible": not reasons,
            "reasons": reasons,
            "game_taps_enabled": False,
        })

    return {
        "engine": "build11ag_accessibility_auditor",
        "groups_checked": len(results),
        "eligible_groups": sum(item["eligible"] for item in results),
        "results": results,
        "source_state_unchanged": True,
        "evidence_verified": False,
        "live_execution_allowed": False,
        "gameplay_actions_performed": False,
        "game_taps_enabled": False,
    }
