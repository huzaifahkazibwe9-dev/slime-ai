import json
from pathlib import Path

BOARD_FILE = Path("data/vision_level39.json")
OBS_FILE = Path("data/conveyor_visual_observations.json")
OUTPUT = Path("data/snapshot_sync_report.json")


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

    synchronised = all(checks.values())

    return {
        "synchronised": synchronised,
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

    checks = {
        "board_snapshot_id_present": isinstance(board_id, str) and bool(board_id),
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
        artifact_ids[name] = snapshot_id
        artifact_sessions[name] = session_id
        checks[f"{name}_artifact_present"] = valid_object
        checks[f"{name}_snapshot_id_present"] = (
            isinstance(snapshot_id, str) and bool(snapshot_id)
        )
        checks[f"{name}_snapshot_matches_board"] = (
            bool(board_id) and snapshot_id == board_id
        )
        checks[f"{name}_session_present"] = (
            isinstance(session_id, str) and bool(session_id)
        )
        checks[f"{name}_session_matches_board"] = (
            bool(board_session) and session_id == board_session
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
