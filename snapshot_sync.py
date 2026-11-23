import json
from datetime import datetime, timezone
from pathlib import Path

BOARD_FILE = Path("data/vision_level39.json")
OBS_FILE = Path("data/conveyor_visual_observations.json")
OUTPUT = Path("data/snapshot_sync_report.json")


def _parse_aware_timestamp(value):
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def validate_capture_freshness(board_timestamp, observation_timestamp,
                               now=None, max_age_seconds=300,
                               max_skew_seconds=120):
    """Require timezone-aware, recent capture times with limited clock skew."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    board_time = _parse_aware_timestamp(board_timestamp)
    observation_time = _parse_aware_timestamp(observation_timestamp)
    checks = {
        "board_timestamp_parseable_and_timezone_aware": board_time is not None,
        "observation_timestamp_parseable_and_timezone_aware": observation_time is not None,
    }
    if board_time is not None:
        age = (now.astimezone(timezone.utc) - board_time).total_seconds()
        checks["board_capture_not_in_future"] = age >= -5
        checks["board_capture_fresh"] = -5 <= age <= max_age_seconds
    else:
        age = None
        checks["board_capture_not_in_future"] = False
        checks["board_capture_fresh"] = False
    if observation_time is not None:
        obs_age = (now.astimezone(timezone.utc) - observation_time).total_seconds()
        checks["observation_capture_not_in_future"] = obs_age >= -5
        checks["observation_capture_fresh"] = -5 <= obs_age <= max_age_seconds
    else:
        obs_age = None
        checks["observation_capture_not_in_future"] = False
        checks["observation_capture_fresh"] = False
    if board_time is not None and observation_time is not None:
        skew = abs((board_time - observation_time).total_seconds())
    else:
        skew = None
    checks["capture_timestamps_within_skew_limit"] = (
        skew is not None and skew <= max_skew_seconds
    )
    return {
        "fresh": all(checks.values()),
        "checks": checks,
        "board_age_seconds": age,
        "observation_age_seconds": obs_age,
        "timestamp_skew_seconds": skew,
        "max_age_seconds": max_age_seconds,
        "max_skew_seconds": max_skew_seconds,
    }


def synchronise_audit(board, observations):
    board_id = board.get("snapshot_id")
    observation_board_id = observations.get("board_snapshot_id")

    board_session = board.get("capture_session_id")
    observation_session = observations.get("capture_session_id")

    checks = {
        "board_snapshot_id_present": bool(board_id),
        "observation_snapshot_id_present": bool(observation_board_id),
        "snapshot_ids_match": (
            bool(board_id) and board_id == observation_board_id
        ),
        "board_session_present": bool(board_session),
        "observation_session_present": bool(observation_session),
        "sessions_match": (
            bool(board_session)
            and board_session == observation_session
        ),
        "same_state_explicitly_confirmed": (
            observations.get("same_board_state_confirmed") is True
        ),
        "board_timestamp_identified": (
            board.get("timestamp_identified") is True
            and bool(board.get("captured_at"))
        ),
        "observation_timestamp_identified": (
            observations.get("timestamp_identified") is True
            and bool(observations.get("captured_at"))
        ),
    }

    freshness = validate_capture_freshness(
        board.get("captured_at"),
        observations.get("captured_at"),
    )
    checks["capture_timestamps_fresh_and_aligned"] = freshness["fresh"]

    synchronised = all(checks.values())

    return {
        "synchronised": synchronised,
        "capture_freshness": freshness,
        "planning_allowed_by_sync": synchronised,
        "checks": checks,
        "board_snapshot_id": board_id,
        "observation_board_snapshot_id": observation_board_id,
        "board_capture_session": board_session,
        "observation_capture_session": observation_session,
        "game_taps_enabled": False,
        "warning": (
            "Matching metadata is necessary but does not prove "
            "that visual detection or gameplay interpretation "
            "is correct."
        ),
    }



def _nested_capture_metadata_consistent(
    artifact,
    require_metadata=False,
    require_observations=False,
    require_tracks=False,
):
    """Check nested visual records cannot contradict their parent capture."""
    if not isinstance(artifact, dict):
        return False
    parent_snapshot = artifact.get("board_snapshot_id")
    parent_session = artifact.get("capture_session_id")
    parent_time = _parse_aware_timestamp(artifact.get("captured_at"))
    if parent_time is None:
        return False

    def check_record(record, required):
        if not isinstance(record, dict):
            return False
        fields = (
            ("board_snapshot_id", parent_snapshot),
            ("capture_session_id", parent_session),
        )
        for field, expected in fields:
            value = record.get(field)
            if required and value != expected:
                return False
            if value is not None and value != expected:
                return False
        identified = record.get("timestamp_identified")
        if required and identified is not True:
            return False
        if identified is not None and identified is not True:
            return False
        value = record.get("captured_at")
        if required and value is None:
            return False
        if value is not None:
            record_time = _parse_aware_timestamp(value)
            if (
                record_time is None
                or abs((record_time - parent_time).total_seconds()) > 120
            ):
                return False
        return True

    if require_observations and "observations" not in artifact:
        return False
    if "observations" in artifact:
        observations = artifact.get("observations")
        if not isinstance(observations, list) or not observations:
            return False
        if not all(check_record(item, require_metadata) for item in observations):
            return False

    if require_tracks and "tracks" not in artifact:
        return False
    if "tracks" in artifact:
        tracks = artifact.get("tracks")
        if not isinstance(tracks, dict) or not tracks:
            return False
        for track in tracks.values():
            if not check_record(track, True):
                return False
            observations = track.get("observations")
            if not isinstance(observations, list) or not observations:
                return False
            if not all(check_record(item, True) for item in observations):
                return False
    return True


def _valid_sha256_snapshot_id(value):
    """Accept only snapshot IDs derived from a full SHA-256 digest."""
    import re
    return isinstance(value, str) and re.fullmatch(
        r"sha256:[0-9a-f]{64}", value
    ) is not None


def synchronise_bundle(board, conveyor, identity, candidates, planning=None):
    """Require every evidence artifact to name the same board capture.

    Missing provenance is a blocker; timestamps or filenames are never
    used to guess that two independently captured artifacts are aligned.
    """
    artifacts = {
        "conveyor": conveyor,
        "identity": identity,
        "candidates": candidates,
        "planning": planning,
    }
    board_id = board.get("snapshot_id") if isinstance(board, dict) else None
    board_session = (
        board.get("capture_session_id") if isinstance(board, dict) else None
    )
    board_captured_at = (
        _parse_aware_timestamp(board.get("captured_at"))
        if isinstance(board, dict) else None
    )

    checks = {
        "board_capture_timestamp_identified": (
            isinstance(board, dict)
            and board.get("timestamp_identified") is True
            and board_captured_at is not None
        ),
        "board_snapshot_id_present": isinstance(board_id, str) and bool(board_id),
        "board_snapshot_id_is_sha256": _valid_sha256_snapshot_id(board_id),
        "board_source_digest_matches_snapshot": (
            isinstance(board, dict)
            and (
                board.get("source_sha256") is None
                or (
                    isinstance(board.get("source_sha256"), str)
                    and _valid_sha256_snapshot_id("sha256:" + board["source_sha256"])
                    and board_id == "sha256:" + board["source_sha256"]
                )
            )
        ),
        "board_capture_session_present": (
            isinstance(board_session, str) and bool(board_session)
        ),
    }
    artifact_ids = {}
    artifact_sessions = {}

    for name, artifact in artifacts.items():
        valid_object = isinstance(artifact, dict)
        snapshot_id = artifact.get("board_snapshot_id") if valid_object else None
        session_id = artifact.get("capture_session_id") if valid_object else None
        artifact_time = (
            _parse_aware_timestamp(artifact.get("captured_at"))
            if valid_object else None
        )
        artifact_ids[name] = snapshot_id
        artifact_sessions[name] = session_id
        checks[f"{name}_artifact_present"] = valid_object
        checks[f"{name}_snapshot_id_present"] = (
            isinstance(snapshot_id, str) and bool(snapshot_id)
        )
        checks[f"{name}_snapshot_matches_board"] = (
            bool(board_id) and snapshot_id == board_id
        )
        source_digest = artifact.get("source_sha256") if valid_object else None
        checks[f"{name}_source_digest_matches_snapshot"] = (
            source_digest is None
            or (
                isinstance(source_digest, str)
                and _valid_sha256_snapshot_id("sha256:" + source_digest)
                and snapshot_id == "sha256:" + source_digest
            )
        )
        checks[f"{name}_session_present"] = (
            isinstance(session_id, str) and bool(session_id)
        )
        checks[f"{name}_session_matches_board"] = (
            bool(board_session) and session_id == board_session
        )
        checks[f"{name}_timestamp_identified"] = (
            valid_object
            and artifact.get("timestamp_identified") is True
            and artifact_time is not None
        )
        checks[f"{name}_timestamp_matches_board"] = (
            board_captured_at is not None
            and artifact_time is not None
            and abs((artifact_time - board_captured_at).total_seconds()) <= 120
        )
        if name in {"conveyor", "candidates"}:
            checks[f"{name}_nested_capture_metadata_consistent"] = (
                _nested_capture_metadata_consistent(
                    artifact,
                    require_metadata=(name == "candidates"),
                    require_observations=(name == "conveyor"),
                    require_tracks=(name == "candidates"),
                )
            )

    synchronised = all(checks.values())
    return {
        "synchronised": synchronised,
        "planning_allowed_by_sync": synchronised,
        "checks": checks,
        "board_snapshot_id": board_id,
        "artifact_snapshot_ids": artifact_ids,
        "board_capture_session": board_session,
        "artifact_capture_sessions": artifact_sessions,
        "board_captured_at": (
            board_captured_at.isoformat() if board_captured_at else None
        ),
        "timestamp_alignment_limit_seconds": 120,
        "game_taps_enabled": False,
        "actions_performed": False,
        "warning": (
            "Every artifact must explicitly reference the same board snapshot "
            "and capture session. Missing provenance is never inferred."
        ),
    }


def main():
    board = json.loads(BOARD_FILE.read_text())
    observations = json.loads(OBS_FILE.read_text())

    report = synchronise_audit(board, observations)
    OUTPUT.write_text(json.dumps(report, indent=2))

    print("SLIME AI — SNAPSHOT SYNCHRONISATION")
    print("=" * 48)

    for name, passed in report["checks"].items():
        print(f"[{'PASS' if passed else 'PENDING'}] {name}")

    print()
    print("Synchronised:", report["synchronised"])
    print("Planning allowed by sync:", report["planning_allowed_by_sync"])
    print("Game taps enabled:", report["game_taps_enabled"])
    print("Report:", OUTPUT)


if __name__ == "__main__":
    main()
