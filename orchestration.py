"""Build 11M: evidence-gated, dry-run-only orchestration."""
import json
from pathlib import Path
from datetime import datetime, timezone


def read_report(path):
    try:
        data = json.loads(Path(path).read_text())
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def evidence_status(planning, identity, snapshot, candidates):
    checks = {
        "planning_report_present": isinstance(planning, dict),
        "identity_report_present": isinstance(identity, dict),
        "snapshot_report_present": isinstance(snapshot, dict),
        "candidate_report_present": isinstance(candidates, dict),
        "planning_has_verified_candidates": (
            isinstance(planning, dict)
            and planning.get("decision") == "ELIGIBLE_CANDIDATES_FOUND"
            and planning.get("gameplay_verified") is True
            and planning.get("actions_performed") is False
        ),
        "identity_verified": (
            isinstance(identity, dict)
            and identity.get("identity_verified") is True
            and identity.get("timestamps_known") is True
            and identity.get("errors") == []
            and identity.get("blockers") == []
        ),
        "snapshot_synchronised": (
            isinstance(snapshot, dict)
            and snapshot.get("synchronised") is True
            and snapshot.get("planning_allowed_by_sync") is True
        ),
        "candidate_identity_verified": (
            isinstance(candidates, dict)
            and candidates.get("identity_verified") is True
        ),
    }
    return {
        "checks": checks,
        "evidence_gate_passed": all(checks.values()),
        "game_taps_enabled": False,
        "actions_performed": False,
    }


def run_orchestration(data_dir="data", candidate_report_path=None):
    from level_loader import load_level
    from planner import plan_next_move

    root = Path(data_dir)
    state, level_audit = load_level()

    planning = read_report(root / "planning_gate_latest.json")
    identity = read_report(root / "identity_audit_report.json")
    snapshot = read_report(root / "snapshot_sync_report.json")

    if candidate_report_path:
        candidate_path = Path(candidate_report_path)
    else:
        candidate_path = root / "candidate_tracking_latest.json"
        for name in (
            "candidate_tracking_latest.json",
            "candidate_tracks_latest.json",
            "candidate_report_latest.json",
        ):
            if (root / name).is_file():
                candidate_path = root / name
                break

    candidates = read_report(candidate_path)
    gate = evidence_status(planning, identity, snapshot, candidates)

    recommended_group = None
    planner_error = None

    if gate["evidence_gate_passed"]:
        try:
            recommended_group = plan_next_move(
                state,
                planning_report=planning,
                identity_audit=identity,
                candidate_report=candidates,
                snapshot_report=snapshot,
            )
        except Exception as exc:
            planner_error = f"{type(exc).__name__}: {exc}"

    dry_summary = None
    dry_error = None

    try:
        from execution_engine import run_dry_simulation
        result = run_dry_simulation(state, max_candidates=25)
        if isinstance(result, dict):
            keys = (
                "candidate_count", "best_score", "removed_pixels",
                "remaining_pixels", "shots", "blocked_attempts",
                "conveyor_used", "evidence_verified",
                "live_execution_allowed", "gameplay_actions_performed",
            )
            dry_summary = {
                key: result[key] for key in keys if key in result
            }
            dry_summary["result_keys"] = sorted(result.keys())
        else:
            dry_summary = {"result_type": type(result).__name__}
    except Exception as exc:
        dry_error = f"{type(exc).__name__}: {exc}"

    report = {
        "build": "11M",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "level": getattr(state, "level", None),
        "level_audit": level_audit,
        "evidence": gate,
        "planner": {
            "recommended_group": (
                list(recommended_group) if recommended_group else None
            ),
            "error": planner_error,
        },
        "dry_simulation": dry_summary,
        "dry_simulation_error": dry_error,
        "decision": (
            "VERIFIED_PLAN_AVAILABLE_BUT_LIVE_ACTIONS_DISABLED"
            if recommended_group else "BLOCKED_NO_VERIFIED_PLAN"
        ),
        "game_taps_enabled": False,
        "live_execution_allowed": False,
        "actions_performed": False,
    }

    root.mkdir(parents=True, exist_ok=True)
    output = root / "orchestration_latest.json"
    temporary = output.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(report, indent=2, default=str))
    temporary.replace(output)

    print("\nSLIME AI — BUILD 11M ORCHESTRATION")
    print("=" * 48)
    print("Evidence gate:",
          "PASS" if gate["evidence_gate_passed"] else "BLOCKED")
    for name, passed in gate["checks"].items():
        print(f"  [{'PASS' if passed else 'PENDING'}] {name}")
    print("Recommended group:", report["planner"]["recommended_group"])
    print("Dry simulation:",
          "completed" if dry_summary is not None else "unavailable")
    if dry_error:
        print("Dry simulation error:", dry_error)
    print("Decision:", report["decision"])
    print("Game taps enabled: False")
    print("Actions performed: False")
    print("Report:", output)
    return report


if __name__ == "__main__":
    run_orchestration()
