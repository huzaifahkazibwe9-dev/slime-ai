"""Build 11M: evidence-gated, dry-run-only orchestration."""
import argparse
import hashlib
import json
import re
import time
from pathlib import Path
from datetime import datetime, timezone


def _valid_snapshot_fingerprint(value):
    return (
        isinstance(value, str)
        and re.fullmatch(r"sha256:[0-9a-f]{64}", value) is not None
    )


def _valid_capture_session_id(value):
    return (
        isinstance(value, str)
        and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", value) is not None
    )


def _valid_aware_capture_timestamp(value):
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


def read_report(path):
    try:
        data = json.loads(Path(path).read_text())
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def _read_json_artifact(path):
    """Read one evidence artifact once, retaining its exact byte digest."""
    path = Path(path)
    try:
        raw = path.read_bytes()
    except OSError:
        return None, None
    digest = hashlib.sha256(raw).hexdigest()
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        value = None
    return (value if isinstance(value, dict) else None), digest


def _read_planning_evidence_bundle(data_dir, candidate_report_path=None):
    """Pin all non-capture reports consumed by one planning pass."""
    root = Path(data_dir)
    candidate_path, candidate_source = resolve_candidate_report_path(
        root, candidate_report_path
    )
    paths = {
        # Pin the direct inputs used to produce the planning gate as well
        # as the derived gate itself. Otherwise an upstream calibration or
        # reachability change could leave a stale planning report looking current.
        "vision_calibration_json": root / "vision_level39.json",
        "edge_confidence_json": root / "edge_confidence_latest.json",
        "reachability_audit_json": root / "reachability_audit.json",
        "reachability_confidence_json": root / "reachability_confidence_latest.json",
        "conveyor_calibration_json": root / "conveyor_calibration.json",
        "planning_json": root / "planning_gate_latest.json",
        "identity_json": root / "identity_audit_report.json",
        "snapshot_json": root / "snapshot_sync_report.json",
        "candidate_json": candidate_path,
        "conveyor_observations_json": root / "conveyor_visual_observations.json",
    }
    values = {}
    digests = {}
    for name, path in paths.items():
        values[name], digests[name] = _read_json_artifact(path)
    return {
        "planning": values["planning_json"],
        "identity": values["identity_json"],
        "snapshot": values["snapshot_json"],
        "candidates": values["candidate_json"],
        "conveyor_observation": values["conveyor_observations_json"],
        "candidate_path": candidate_path,
        "candidate_path_source": candidate_source,
        "file_sha256": digests,
    }


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



def _capture_metadata_matches(planning, identity, snapshot, candidates):
    sources = (planning, identity, snapshot, candidates)
    if not all(isinstance(item, dict) for item in sources):
        return False
    fingerprint = identity.get("board_snapshot_id")
    session = identity.get("capture_session_id")
    captured = identity.get("captured_at")
    if not _valid_snapshot_fingerprint(fingerprint) or not _valid_capture_session_id(session) or not _valid_aware_capture_timestamp(captured):
        return False
    base_time = datetime.fromisoformat(captured.replace("Z", "+00:00"))
    for source in (planning, snapshot, candidates):
        source_time_text = source.get("captured_at")
        if (
            source.get("board_snapshot_id") != fingerprint
            or source.get("capture_session_id") != session
            or source.get("timestamp_identified") is not True
            or not _valid_aware_capture_timestamp(source_time_text)
        ):
            return False
        source_time = datetime.fromisoformat(source_time_text.replace("Z", "+00:00"))
        if abs((source_time - base_time).total_seconds()) > 120:
            return False
    return True

def evidence_status(planning, identity, snapshot, candidates, shooter_capture_verified=False):
    checks = {
        "shooter_capture_provenance_verified": shooter_capture_verified is True,
        "planning_report_present": isinstance(planning, dict),
        "identity_report_present": isinstance(identity, dict),
        "snapshot_report_present": isinstance(snapshot, dict),
        "candidate_report_present": isinstance(candidates, dict),
        "planning_conveyor_timing_calibrated": (
            isinstance(planning, dict)
            and planning.get("conveyor_timing_calibrated") is True
        ),
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
            and planning.get("planning_evidence_verified") is True
            and planning.get("gameplay_verified") is False
            and planning.get("actions_performed") is False
            and planning.get("game_taps_enabled") is False
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
            and _valid_snapshot_fingerprint(identity.get("board_snapshot_id"))
        ),
        "identity_capture_session_provenance_complete": (
            isinstance(identity, dict)
            and identity.get("capture_session_linked") is True
            and _valid_capture_session_id(identity.get("capture_session_id"))
            and identity.get("timestamp_identified") is True
            and _valid_aware_capture_timestamp(identity.get("captured_at"))
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
        "all_evidence_sources_share_capture": _capture_metadata_matches(
            planning, identity, snapshot, candidates
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
                                  max_depth=None, result=None):
    """Run evolving-board search without inferring dynamic accessibility."""
    try:
        if result is None:
            from evolving_board_planner import plan_evolving_board
            result = plan_evolving_board(
                state, accessibility_resolver=None, max_nodes=max_nodes,
                beam_width=beam_width, max_depth=max_depth,
            )
        return {
            "engine": result.get("engine"),
            "status": result.get("status"),
            "nodes_examined": result.get("nodes_examined", 0),
            "search_performance": result.get("performance", {}),
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

def run_capacity_aware_evolving_diagnostic(state, max_nodes=500, beam_width=40,
                                           board_plan=None):
    """Run evolving-board planning with conservative capacity batches."""
    try:
        from capacity_aware_evolving_planner import plan_capacity_aware_evolving_schedule
        result = plan_capacity_aware_evolving_schedule(
            state, accessibility_resolver=None,
            max_nodes=max_nodes, beam_width=beam_width,
            board_plan=board_plan,
        )
        return {
            "engine": result.get("engine"),
            "status": result.get("status"),
            "sequence": result.get("board_plan", {}).get("sequence", []),
            "board_search_performance": result.get("board_plan", {}).get("performance", {}),
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


def _read_capture_bundle(observation_path, shooter_path, pixel_audit_path=None):
    """Read each mutable capture artifact once and pin its parsed JSON objects."""
    observation_path = Path(observation_path)
    shooter_path = Path(shooter_path)
    audit_path = (
        Path(pixel_audit_path)
        if pixel_audit_path is not None
        else observation_path.parent / "source_pixel_audit_latest.json"
    )
    try:
        board_bytes = observation_path.read_bytes()
        shooter_bytes = shooter_path.read_bytes()
        audit_bytes = audit_path.read_bytes()
        board = json.loads(board_bytes)
        shooters = json.loads(shooter_bytes)
        pixel_audit = json.loads(audit_bytes)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Capture bundle is missing or invalid: {exc}") from exc
    if not all(isinstance(item, dict) for item in (board, shooters, pixel_audit)):
        raise ValueError("Capture bundle files must each contain a JSON object.")
    return {
        "board_data": board,
        "shooter_data": shooters,
        "pixel_audit_data": pixel_audit,
        "board_bytes_sha256": hashlib.sha256(board_bytes).hexdigest(),
        "shooter_bytes_sha256": hashlib.sha256(shooter_bytes).hexdigest(),
        "pixel_audit_bytes_sha256": hashlib.sha256(audit_bytes).hexdigest(),
    }


def run_orchestration(data_dir="data", candidate_report_path=None,
                      observation_path=None, shooter_path=None):
    if observation_path is None or shooter_path is None:
        raise ValueError(
            "Explicit board observation and shooter capture paths are required; "
            "legacy baseline fallback is disabled for orchestration."
        )
    from capture_preflight import validate_capture_pair
    pinned_capture = _read_capture_bundle(observation_path, shooter_path)
    capture = validate_capture_pair(
        observation_path,
        shooter_path,
        board_data=pinned_capture["board_data"],
        shooter_data=pinned_capture["shooter_data"],
        pixel_audit_data=pinned_capture["pixel_audit_data"],
    )
    if capture.get("valid") is not True:
        raise ValueError(capture.get("reason", "Capture preflight failed."))
    # All downstream stages use the validated in-memory objects, not paths.
    board_observation = capture["board_data"]
    shooter_observation = capture["shooter_data"]

    pipeline_started = time.perf_counter()
    timings = {}
    from level_loader import load_level
    from planner import plan_next_move

    root = Path(data_dir)
    stage_started = time.perf_counter()
    state, level_audit = load_level(
        observation_path=observation_path,
        shooter_path=shooter_path,
        observation_data=board_observation,
        shooter_data=shooter_observation,
    )
    timings["level_loading_seconds"] = round(time.perf_counter() - stage_started, 6)

    evidence_bundle = _read_planning_evidence_bundle(
        root, candidate_report_path
    )
    planning = evidence_bundle["planning"]
    identity = evidence_bundle["identity"]
    snapshot = evidence_bundle["snapshot"]
    candidates = evidence_bundle["candidates"]
    candidate_path = evidence_bundle["candidate_path"]
    candidate_path_source = evidence_bundle["candidate_path_source"]

    # Cross-link every evidence source to one explicitly identified board
    # capture. Missing metadata blocks planning rather than being inferred.
    from snapshot_sync import synchronise_bundle
    conveyor_observation = evidence_bundle["conveyor_observation"]
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

    stage_started = time.perf_counter()
    gate = evidence_status(
        planning, identity, snapshot, candidates,
        shooter_capture_verified=(
            level_audit.get("shooter_capture_provenance_verified") is True
        ),
    )
    timings["evidence_gate_seconds"] = round(time.perf_counter() - stage_started, 6)

    recommended_group = None
    planner_error = None
    stage_started = time.perf_counter()

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
    timings["move_planner_seconds"] = round(time.perf_counter() - stage_started, 6)

    dry_summary = None
    dry_error = None

    stage_started = time.perf_counter()
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
    timings["dry_simulation_seconds"] = round(time.perf_counter() - stage_started, 6)

    # Search whole-batch sequences as a separate bounded planning pass.
    # It remains simulation-only and cannot authorize Android input.
    stage_started = time.perf_counter()
    multi_batch_summary = run_multi_batch_diagnostic(
        state,
        max_candidates=200,
    )
    timings["multi_batch_search_seconds"] = round(time.perf_counter() - stage_started, 6)
    stage_started = time.perf_counter()
    from evolving_board_planner import plan_evolving_board
    shared_board_plan = plan_evolving_board(
        state, accessibility_resolver=None, max_nodes=500, beam_width=40,
    )
    evolving_board_summary = run_evolving_board_diagnostic(
        state, max_nodes=500, beam_width=40, result=shared_board_plan,
    )
    timings["evolving_board_search_seconds"] = round(time.perf_counter() - stage_started, 6)
    stage_started = time.perf_counter()
    capacity_evolving_summary = run_capacity_aware_evolving_diagnostic(
        state, max_nodes=500, beam_width=40, board_plan=shared_board_plan,
    )
    timings["capacity_aware_search_seconds"] = round(time.perf_counter() - stage_started, 6)
    timings["bounded_searches_seconds"] = round(
        timings["multi_batch_search_seconds"]
        + timings["evolving_board_search_seconds"]
        + timings["capacity_aware_search_seconds"], 6
    )
    timings["orchestration_total_seconds"] = round(time.perf_counter() - pipeline_started, 6)

    report = {
        "build": "11M",
        "capture_bundle_file_sha256": {
            "board_json": pinned_capture["board_bytes_sha256"],
            "shooter_json": pinned_capture["shooter_bytes_sha256"],
            "pixel_audit_json": pinned_capture["pixel_audit_bytes_sha256"],
        },
        "planning_evidence_file_sha256": evidence_bundle["file_sha256"],
        "capture_provenance": {
            key: board_observation.get(key)
            for key in (
                "source_sha256", "capture_session_id", "captured_at",
                "snapshot_id", "board_snapshot_id",
            )
        },
        "created_at": datetime.now(timezone.utc).isoformat(),
        "performance": {
            "timing_clock": "time.perf_counter",
            "stage_seconds": timings,
            "note": "Local diagnostic timings only; not gameplay latency or a device speed guarantee.",
        },
        "level": getattr(state, "level", None),
        "level_audit": level_audit,
        "shooter_observation_quality": level_audit.get(
            "shooter_observation_quality",
            {
                "colour_independently_verified": False,
                "ammunition_independently_verified": False,
                "slot_mapping_independently_verified": False,
                "interpretation": "Shooter visual quality metadata is unavailable.",
            },
        ),
        "plan_verification_status": (
            "SIMULATION_CANDIDATE_ONLY_NOT_GAMEPLAY_VERIFIED"
            if recommended_group else "NO_CANDIDATE_PLAN"
        ),
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
            "recommendation_status": (
                "SIMULATION_CANDIDATE_ONLY_NOT_GAMEPLAY_VERIFIED"
                if recommended_group else "NO_CANDIDATE_PLAN"
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
