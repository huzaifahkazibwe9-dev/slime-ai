from game_state import GameState

SNAPSHOT_CHECKS = (
    "board_snapshot_id_present",
    "observation_snapshot_id_present",
    "snapshot_ids_match",
    "board_session_present",
    "observation_session_present",
    "sessions_match",
    "same_state_explicitly_confirmed",
    "board_timestamp_identified",
    "observation_timestamp_identified",
)


def evaluate_group(state, group, board_colours=None):
    if board_colours is None:
        board_colours = {
            p for row in state.board for p in row if p is not None
        }
    score = 0
    for shooter_id in group:
        shooter = state.shooters[shooter_id]
        if shooter.color in board_colours:
            score += 10
        if shooter.ammo is not None and shooter.ammo > 0:
            score += 2
    return score


def available_groups(state):
    seen = set()
    for shooter in state.accessible_shooters():
        group = state.bonded_group(shooter.id)
        if not group:
            continue
        key = tuple(sorted(group))
        if key in seen or not state.can_select_group(shooter.id):
            continue
        seen.add(key)
        yield tuple(group)


def _valid_sha256(value):
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _source_provenance_matches(
    state, identity, planning, candidates, snapshot,
    current_source_file_sha256, current_calibration_sha256,
    current_identity_audit, current_board_observation,
):
    """Bind every planning report to the exact inputs pinned for this pass."""
    if not isinstance(current_source_file_sha256, dict):
        return False
    if (
        not isinstance(identity, dict)
        or not isinstance(current_identity_audit, dict)
        or identity != current_identity_audit
        or not isinstance(current_board_observation, dict)
    ):
        return False
    current_board_snapshot_id = current_board_observation.get("snapshot_id")
    current_board_source_sha256 = current_board_observation.get("source_sha256")
    if (
        not isinstance(current_board_source_sha256, str)
        or not _valid_sha256(current_board_source_sha256)
        or current_board_snapshot_id != "sha256:" + current_board_source_sha256
        or getattr(state, "snapshot_id", None) != current_board_snapshot_id
        or getattr(state, "capture_session_id", None)
        != current_board_observation.get("capture_session_id")
        or current_board_observation.get("calibration_sha256")
        != getattr(state, "calibration_sha256", None)
    ):
        return False
    required_inputs = (
        "vision_calibration_json",
        "edge_confidence_json",
        "reachability_audit_json",
        "reachability_confidence_json",
        "conveyor_calibration_json",
        "planning_json",
        "identity_json",
        "snapshot_json",
        "candidate_json",
        "conveyor_observations_json",
        "shooter_detection_json",
        "board_observation_json",
    )
    if any(
        not _valid_sha256(current_source_file_sha256.get(name))
        for name in required_inputs
    ):
        return False

    expected_snapshot = {
        "vision_level39_json": current_source_file_sha256["vision_calibration_json"],
        "conveyor_observations_json": current_source_file_sha256[
            "conveyor_observations_json"
        ],
    }
    if (
        not isinstance(snapshot, dict)
        or snapshot.get("source_file_sha256") != expected_snapshot
    ):
        return False

    expected_planning = {
        "reachability_confidence_json": current_source_file_sha256[
            "reachability_confidence_json"
        ],
        "candidate_json": current_source_file_sha256["candidate_json"],
        "conveyor_calibration_json": current_source_file_sha256[
            "conveyor_calibration_json"
        ],
    }
    if (
        not isinstance(planning, dict)
        or planning.get("input_file_sha256") != expected_planning
    ):
        return False

    expected_candidates = {
        "conveyor_calibration_json": current_source_file_sha256[
            "conveyor_calibration_json"
        ],
        "conveyor_visual_observations_json": current_source_file_sha256[
            "conveyor_observations_json"
        ],
        "shooter_detection_json": current_source_file_sha256[
            "shooter_detection_json"
        ],
    }
    if (
        not isinstance(candidates, dict)
        or candidates.get("source_file_sha256") != expected_candidates
    ):
        return False

    source_kind = planning.get("upstream_source_kind")
    if source_kind == "screenshot_observation":
        expected_confidence = {
            "reachability_audit_json": current_source_file_sha256[
                "reachability_audit_json"
            ],
            "board_observation_json": current_source_file_sha256[
                "board_observation_json"
            ],
        }
        expected_upstream = {
            "board_json": current_source_file_sha256["board_observation_json"],
            "conveyor_calibration_json": current_source_file_sha256[
                "conveyor_calibration_json"
            ],
            "conveyor_observations_json": current_source_file_sha256[
                "conveyor_observations_json"
            ],
        }
    elif source_kind == "baseline_board":
        expected_confidence = {
            "reachability_audit_json": current_source_file_sha256[
                "reachability_audit_json"
            ],
            "vision_level39_json": current_source_file_sha256[
                "vision_calibration_json"
            ],
            "edge_confidence_json": current_source_file_sha256[
                "edge_confidence_json"
            ],
        }
        expected_upstream = {
            "board_json": current_source_file_sha256["vision_calibration_json"],
            "conveyor_calibration_json": current_source_file_sha256[
                "conveyor_calibration_json"
            ],
            "conveyor_observations_json": current_source_file_sha256[
                "conveyor_observations_json"
            ],
        }
    else:
        return False

    if (
        not isinstance(planning.get("confidence_source_file_sha256"), dict)
        or planning.get("confidence_source_file_sha256") != expected_confidence
        or not isinstance(planning.get("upstream_source_file_sha256"), dict)
        or planning.get("upstream_source_file_sha256") != expected_upstream
    ):
        return False

    board_calibration_sha256 = getattr(state, "calibration_sha256", None)
    return (
        _valid_sha256(board_calibration_sha256)
        and _valid_sha256(current_calibration_sha256)
        and board_calibration_sha256 == current_calibration_sha256
    )


def _verified_identity_mapping(state, identity, candidates, snapshot):
    """Derive current shooter positions from independently verified reports."""
    if not all(isinstance(x, dict) for x in (identity, candidates, snapshot)):
        return None

    if (
        identity.get("identity_verified") is not True
        or identity.get("timestamps_known") is not True
        or identity.get("errors") != []
        or identity.get("blockers") != []
        or type(identity.get("positions_checked")) is not int
        or identity["positions_checked"] < 1
    ):
        return None

    checks = candidates.get("checks")
    required = (
        "four_sides_in_expected_order",
        "eight_observations_present",
        "two_candidate_tracks_supported",
        "candidate_pair_is_user_confirmed_bond",
        "timestamps_known",
        "identity_previously_verified",
        "current_snapshot_identified",
    )
    if (
        candidates.get("identity_verified") is not True
        or not isinstance(checks, dict)
        or any(checks.get(k) is not True for k in required)
    ):
        return None

    sync_checks = snapshot.get("checks")
    if (
        snapshot.get("synchronised") is not True
        or snapshot.get("planning_allowed_by_sync") is not True
        or not isinstance(sync_checks, dict)
        or any(sync_checks.get(k) is not True for k in SNAPSHOT_CHECKS)
    ):
        return None

    snapshot_id = candidates.get("current_snapshot_id")
    state_snapshot_id = getattr(state, "snapshot_id", None)
    if (
        not isinstance(snapshot_id, str)
        or not snapshot_id
        or not isinstance(state_snapshot_id, str)
        or state_snapshot_id != snapshot_id
        or snapshot.get("board_snapshot_id") != snapshot_id
        or snapshot.get("observation_board_snapshot_id") != snapshot_id
    ):
        return None

    tracks = candidates.get("tracks")
    known = identity.get("known_shooters")
    if not isinstance(tracks, dict) or not tracks or not isinstance(known, list):
        return None

    mapping = {}
    for track in tracks.values():
        if not isinstance(track, dict):
            return None

        shooter_id = track.get("candidate_shooter")
        position_id = track.get("current_position_id")
        observations = track.get("observations")

        if (
            not isinstance(shooter_id, str)
            or shooter_id not in state.shooters
            or shooter_id not in known
            or not isinstance(position_id, str)
            or not isinstance(observations, list)
            or any(
                track.get(k) is not True
                for k in (
                    "candidate_supported",
                    "ammo_non_increasing",
                    "panel_colour_match",
                    "observed_colour_consistent",
                )
            )
        ):
            return None

        current = [
            obs for obs in observations
            if isinstance(obs, dict)
            and obs.get("position_id") == position_id
        ]
        if len(current) != 1:
            return None

        obs = current[0]
        shooter = state.shooters[shooter_id]
        if (
            obs.get("colour") != track.get("panel_colour")
            or obs.get("colour") != shooter.color
            or type(obs.get("ammo")) is not int
            or obs["ammo"] <= 0
        ):
            return None

        if position_id in mapping:
            return None
        mapping[position_id] = shooter_id

    if len(set(mapping.values())) != len(mapping):
        return None

    return mapping


def _verified_group(state, group, report, mapping):
    if (
        not isinstance(report, dict)
        or report.get("planning_evidence_verified") is not True
        or report.get("gameplay_verified") is not False
        or report.get("game_taps_enabled") is not False
        or report.get("actions_performed") is not False
        or (state.level is not None and report.get("level") != state.level)
    ):
        return False

    results = report.get("results")
    if not isinstance(results, list) or not isinstance(mapping, dict):
        return False

    reverse = {}
    for position, shooter_id in mapping.items():
        if not isinstance(position, str) or not isinstance(shooter_id, str):
            return False
        reverse.setdefault(shooter_id, []).append(position)

    for shooter_id in group:
        shooter = state.shooters[shooter_id]
        positions = reverse.get(shooter_id, [])
        if len(positions) != 1:
            return False

        matches = [
            item for item in results
            if isinstance(item, dict)
            and item.get("position_id") == positions[0]
            and item.get("target_colour") == shooter.color
        ]
        if len(matches) != 1:
            return False

        item = matches[0]
        if (
            item.get("planning_eligible") is not True
            or item.get("geometrically_reachable") is not True
            or item.get("ammunition_available") is not True
            or item.get("ammunition_evidence_verified") is not True
            or type(item.get("observed_ammo")) is not int
            or item["observed_ammo"] <= 0
            or type(item.get("exposed_matching_count")) is not int
            or item["exposed_matching_count"] <= 0
            or item.get("blockers") != []
            or shooter.ammo is None
            or shooter.ammo != item["observed_ammo"]
        ):
            return False

    return True


def plan_next_move(
    state,
    planning_report=None,
    identity_audit=None,
    candidate_report=None,
    snapshot_report=None,
    current_source_file_sha256=None,
    current_calibration_sha256=None,
    current_identity_audit=None,
    current_board_observation=None,
):
    """Return a group only when current source provenance also matches."""
    if state.validate():
        return None
    if getattr(state, "shooter_capture_provenance_verified", False) is not True:
        return None
    if not _source_provenance_matches(
        state,
        identity_audit,
        planning_report,
        candidate_report,
        snapshot_report,
        current_source_file_sha256,
        current_calibration_sha256,
        current_identity_audit,
        current_board_observation,
    ):
        return None

    mapping = _verified_identity_mapping(
        state, identity_audit, candidate_report, snapshot_report
    )
    if mapping is None:
        return None

    # Board colours are invariant across candidate groups. Build the set once
    # instead of rescanning the complete board for every candidate.
    board_colours = {
        pixel for row in state.board for pixel in row if pixel is not None
    }
    eligible = []
    for group in available_groups(state):
        if _verified_group(state, group, planning_report, mapping):
            eligible.append((evaluate_group(state, group, board_colours), group))

    if not eligible:
        return None

    eligible.sort(
        key=lambda item: (item[0], -len(item[1]), item[1]),
        reverse=True,
    )
    return eligible[0][1]


if __name__ == "__main__":
    import json
    from pathlib import Path
    from level_loader import load_level

    state, _ = load_level()

    def read_report(filename):
        path = Path("data") / filename
        return json.loads(path.read_text()) if path.exists() else None

    planning = read_report("planning_gate_latest.json")
    identity = read_report("identity_audit_report.json")
    candidates = read_report("conveyor_identity_candidates.json")
    snapshot = read_report("snapshot_sync_report.json")
    from orchestration import (
        _canonical_json_sha256,
        _read_planning_evidence_bundle,
    )
    evidence_bundle = _read_planning_evidence_bundle(Path("data"))
    planning = evidence_bundle["planning"]
    identity = evidence_bundle["identity"]
    candidates = evidence_bundle["candidates"]
    snapshot = evidence_bundle["snapshot"]

    result = plan_next_move(
        state, planning, identity, candidates, snapshot,
        current_source_file_sha256=evidence_bundle["file_sha256"],
        current_calibration_sha256=_canonical_json_sha256(
            evidence_bundle["vision_calibration"]
        ),
    )

    print("SLIME AI — BUILD 11J EVIDENCE-BOUND PLANNER")
    print("=" * 52)
    print("Level:", state.level)
    print("Accessible shooters:", len(state.accessible_shooters()))
    print("Identity audit verified:", bool(identity and identity.get("identity_verified") is True))
    print("Snapshot synchronised:", bool(snapshot and snapshot.get("synchronised") is True))
    print("Planning gameplay verified:", bool(planning and planning.get("gameplay_verified") is True))
    print("Recommended group:", result)
    print("Game taps enabled: False")
