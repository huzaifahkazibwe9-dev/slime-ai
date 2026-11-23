"""Build 11M: evidence-gated, dry-run-only orchestration."""
import argparse
import json
from pathlib import Path
from datetime import datetime, timezone


def read_report(path):
    try:
        data = json.loads(Path(path).read_text())
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def resolve_candidate_report_path(data_dir, explicit_path=None):
    """Prefer the canonical matcher output; never silently override an explicit path."""
    if explicit_path is not None:
        return Path(explicit_path), "explicit"

    root = Path(data_dir)
    candidates = (
        "conveyor_identity_candidates.json",
        "candidate_tracking_latest.json",
        "candidate_tracks_latest.json",
        "candidate_report_latest.json",
    )
    for name in candidates:
        path = root / name
        if path.is_file():
            return path, "canonical" if name == candidates[0] else "legacy_fallback"
    return root / candidates[0], "missing"


def evidence_status(planning, identity, snapshot, candidates):
    checks = {
        "planning_report_present": isinstance(planning, dict),
        "identity_report_present": isinstance(identity, dict),
        "snapshot_report_present": isinstance(snapshot, dict),
        "candidate_report_present": isinstance(candidates, dict),
        "planning_capture_freshness_verified": (
            isinstance(planning, dict)
            and planning.get("capture_freshness_verified") is True
        ),
        "planning_candidate_capture_provenance_verified": (
            isinstance(planning, dict)
            and planning.get("candidate_capture_provenance_verified") is True
        ),
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
        "identity_snapshot_provenance_complete": (
            isinstance(identity, dict)
            and identity.get("snapshot_linked") is True
            and isinstance(identity.get("board_snapshot_id"), str)
            and identity.get("board_snapshot_id").startswith("sha256:")
        ),
        "identity_capture_session_provenance_complete": (
            isinstance(identity, dict)
            and identity.get("capture_session_linked") is True
            and isinstance(identity.get("capture_session_id"), str)
            and bool(identity.get("capture_session_id").strip())
            and identity.get("timestamp_identified") is True
            and isinstance(identity.get("captured_at"), str)
            and bool(identity.get("captured_at").strip())
        ),
        "snapshot_synchronised": (
            isinstance(snapshot, dict)
            and snapshot.get("synchronised") is True
            and snapshot.get("planning_allowed_by_sync") is True
        ),
        "evidence_bundle_synchronised": (
            isinstance(snapshot, dict)
            and isinstance(snapshot.get("bundle_synchronisation"), dict)
            and snapshot["bundle_synchronisation"].get("synchronised") is True
            and snapshot["bundle_synchronisation"].get(
                "planning_allowed_by_sync"
            ) is True
        ),
        "candidate_identity_verified": (
            isinstance(candidates, dict)
            and candidates.get("identity_verified") is True
        ),
        "candidate_capture_provenance_verified": (
            isinstance(candidates, dict)
            and candidates.get("candidate_provenance_verified") is True
        ),
    }
    return {
        "checks": checks,
        "evidence_gate_passed": all(checks.values()),
        "game_taps_enabled": False,
        "actions_performed": False,
    }



def run_multi_batch_diagnostic(state, max_candidates=200):
    """Run bounded multi-batch search and retain a compact, simulation-only summary."""
    try:
        from multi_batch_candidate_planner import plan_multi_batch_candidates

        result = plan_multi_batch_candidates(
            state,
            max_candidates=max_candidates,
        )
        best = result.get("best")
        best_summary = None
        if isinstance(best, dict):
            best_summary = {
                "schedule_valid": best.get("schedule_valid") is True,
                "candidate_order": list(best.get("candidate_order", [])),
                "candidate_batches": best.get("candidate_batches", []),
                "pixels_removed": best.get("simulated_pixels_removed", 0),
                "remaining_pixels": best.get("simulated_remaining_pixels"),
            }

        return {
            "engine": result.get("engine"),
            "status": result.get("status"),
            "accessible_group_count": result.get("accessible_group_count", 0),
            "candidate_count": result.get("candidate_count", 0),
            "valid_candidate_count": result.get("valid_candidate_count", 0),
            "search_truncated": result.get("search_truncated", False),
            "best": best_summary,
            "completion": result.get("completion", {
                "full_level_complete": False,
                "blockers": ["COMPLETION_AUDIT_UNAVAILABLE"],
            }),
            "source_state_unchanged": result.get("source_state_unchanged") is True,
            "evidence_verified": False,
            "live_execution_allowed": False,
            "gameplay_actions_performed": False,
            "game_taps_enabled": False,
            "limitations": result.get("limitations", []),
        }
    except Exception as exc:
        return {
            "status": "MULTI_BATCH_DIAGNOSTIC_ERROR",
            "error": f"{type(exc).__name__}: {exc}",
            "evidence_verified": False,
            "live_execution_allowed": False,
            "gameplay_actions_performed": False,
            "game_taps_enabled": False,
        }


def run_evolving_board_diagnostic(state, max_nodes=500, beam_width=40,
                                  max_depth=None):
    """Run evolving-board search without inferring dynamic accessibility."""
    try:
        from evolving_board_planner import plan_evolving_board
        result = plan_evolving_board(
            state, accessibility_resolver=None, max_nodes=max_nodes,
            beam_width=beam_width, max_depth=max_depth,
        )
        return {
            "engine": result.get("engine"),
            "status": result.get("status"),
            "nodes_examined": result.get("nodes_examined", 0),
            "search_truncated": result.get("search_truncated", False),
            "sequence": result.get("sequence", []),
            "sequence_length": result.get("sequence_length", 0),
            "initial_pixels": result.get("initial_pixels"),
            "simulated_pixels_removed": result.get("simulated_pixels_removed", 0),
            "simulated_remaining_pixels": result.get("simulated_remaining_pixels"),
            "board_cleared": result.get("board_cleared") is True,
            "known_group_count": result.get("known_group_count", 0),
            "unplanned_group_ids": result.get("unplanned_group_ids", []),
            "full_level_complete": False,
            "blockers": list(result.get("blockers", [])),
            "source_state_unchanged": result.get("source_state_unchanged") is True,
            "evidence_verified": False,
            "live_execution_allowed": False,
            "gameplay_actions_performed": False,
            "game_taps_enabled": False,
            "limitations": result.get("limitations", []),
        }
    except Exception as exc:
        return {
            "status": "EVOLVING_BOARD_DIAGNOSTIC_ERROR",
            "error": f"{type(exc).__name__}: {exc}",
            "full_level_complete": False,
            "evidence_verified": False,
            "live_execution_allowed": False,
            "gameplay_actions_performed": False,
            "game_taps_enabled": False,
        }

def run_capacity_aware_evolving_diagnostic(state, max_nodes=500, beam_width=40):
    """Run evolving-board planning with conservative capacity batches."""
    try:
        from capacity_aware_evolving_planner import plan_capacity_aware_evolving_schedule
        result = plan_capacity_aware_evolving_schedule(
            state, accessibility_resolver=None,
            max_nodes=max_nodes, beam_width=beam_width,
        )
        return {
            "engine": result.get("engine"),
            "status": result.get("status"),
            "sequence": result.get("board_plan", {}).get("sequence", []),
            "batches": result.get("batches", []),
            "schedule_valid": result.get("schedule_valid") is True,
            "initial_pixels": result.get("initial_pixels"),
            "simulated_pixels_removed": result.get("simulated_pixels_removed", 0),
            "simulated_remaining_pixels": result.get("simulated_remaining_pixels"),
            "board_cleared": result.get("board_cleared") is True,
            "known_group_count": result.get("known_group_count", 0),
            "planned_group_count": result.get("planned_group_count", 0),
            "unplanned_group_ids": result.get("unplanned_group_ids", []),
            "full_level_complete": False,
            "blockers": list(result.get("blockers", [])),
            "source_state_unchanged": result.get("source_state_unchanged") is True,
            "evidence_verified": False,
            "live_execution_allowed": False,
            "gameplay_actions_performed": False,
            "game_taps_enabled": False,
            "limitations": result.get("limitations", []),
        }
    except Exception as exc:
        return {
            "status": "CAPACITY_AWARE_DIAGNOSTIC_ERROR",
            "error": f"{type(exc).__name__}: {exc}",
            "full_level_complete": False,
            "evidence_verified": False,
            "live_execution_allowed": False,
            "gameplay_actions_performed": False,
            "game_taps_enabled": False,
        }

def run_orchestration(data_dir="data", candidate_report_path=None,
                      observation_path=None, shooter_path=None):
    from level_loader import load_level
    from planner import plan_next_move

    root = Path(data_dir)
    state, level_audit = load_level(
        observation_path=observation_path,
        shooter_path=shooter_path,
    )

    planning = read_report(root / "planning_gate_latest.json")
    identity = read_report(root / "identity_audit_report.json")
    snapshot = read_report(root / "snapshot_sync_report.json")

    candidate_path, candidate_path_source = resolve_candidate_report_path(
        root, candidate_report_path
    )
    candidates = read_report(candidate_path)

    # Cross-link every evidence source to one explicitly identified board
    # capture. Missing metadata blocks planning rather than being inferred.
    from snapshot_sync import synchronise_bundle
    board_observation = read_report(root / "board_observation_latest.json")
    conveyor_observation = read_report(root / "conveyor_visual_observations.json")
    bundle_sync = synchronise_bundle(
        board_observation,
        conveyor_observation,
        identity,
        candidates,
        planning,
    )
    snapshot = dict(snapshot) if isinstance(snapshot, dict) else {}
    snapshot["synchronised"] = (
        snapshot.get("synchronised") is True
        and bundle_sync["synchronised"]
    )
    snapshot["planning_allowed_by_sync"] = (
        snapshot.get("planning_allowed_by_sync") is True
        and bundle_sync["planning_allowed_by_sync"]
    )
    snapshot["bundle_synchronisation"] = bundle_sync

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

    # Search whole-batch sequences as a separate bounded planning pass.
    # It remains simulation-only and cannot authorize Android input.
    multi_batch_summary = run_multi_batch_diagnostic(
        state,
        max_candidates=200,
    )
    evolving_board_summary = run_evolving_board_diagnostic(
        state, max_nodes=500, beam_width=40,
    )
    capacity_evolving_summary = run_capacity_aware_evolving_diagnostic(
        state, max_nodes=500, beam_width=40,
    )

    report = {
        "build": "11M",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "level": getattr(state, "level", None),
        "level_audit": level_audit,
        "candidate_report": {
            "path": str(candidate_path),
            "selection_source": candidate_path_source,
            "loaded": isinstance(candidates, dict),
        },
        "evidence": gate,
        "evidence_bundle_synchronisation": bundle_sync,
        "planner": {
            "recommended_group": (
                list(recommended_group) if recommended_group else None
            ),
            "error": planner_error,
        },
        "dry_simulation": dry_summary,
        "dry_simulation_error": dry_error,
        "multi_batch_planning": multi_batch_summary,
        "evolving_board_planning": evolving_board_summary,
        "capacity_aware_evolving_planning": capacity_evolving_summary,
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
    print("Evolving-board search:", evolving_board_summary.get("status", "unavailable"))
    print("Capacity-aware evolving schedule:", capacity_evolving_summary.get("status", "unavailable"))
    if dry_error:
        print("Dry simulation error:", dry_error)
    print("Decision:", report["decision"])
    print("Game taps enabled: False")
    print("Actions performed: False")
    print("Report:", output)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Run evidence-gated, dry-run-only Slime AI orchestration"
    )
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--candidate-report")
    parser.add_argument(
        "--observation",
        help="Use a screenshot-ingestor board observation instead of the legacy baseline",
    )
    parser.add_argument(
        "--shooters",
        default="data/shooter_detection.json",
        help="Shooter detection JSON (used with --observation)",
    )
    args = parser.parse_args()
    run_orchestration(
        data_dir=args.data_dir,
        candidate_report_path=args.candidate_report,
        observation_path=args.observation,
        shooter_path=args.shooters if args.observation else None,
    )
