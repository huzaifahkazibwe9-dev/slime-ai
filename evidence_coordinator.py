import json
import hashlib
from pathlib import Path
from datetime import datetime, timezone

from screenshot_ingestor import extract_board, BASELINE

REPORT = Path("data/evidence_coordinator_latest.json")
OBSERVATION = Path("data/board_observation_latest.json")


EDGE_WIDTH = 2


def is_edge(row, col, rows, cols, width=EDGE_WIDTH):
    """Identify the calibrated outer perimeter without changing board data."""
    if width < 1 or rows < 2 * width + 1 or cols < 2 * width + 1:
        raise ValueError("Invalid edge width for board dimensions")

    return (
        row < width
        or col < width
        or row >= rows - width
        or col >= cols - width
    )


def audit_transition(previous, current):
    if not isinstance(previous, list) or not isinstance(current, list):
        raise ValueError("Boards must be lists")

    if not previous or len(previous) != len(current):
        raise ValueError("Board dimensions do not match")

    rows = len(previous)
    cols = len(previous[0])

    if cols == 0 or any(len(r) != cols for r in previous + current):
        raise ValueError("Boards must be rectangular")

    changes = []
    edge_changes = []
    interior_changes = []

    for r in range(rows):
        for c in range(cols):
            if previous[r][c] != current[r][c]:
                item = {
                    "row": r,
                    "column": c,
                    "before": previous[r][c],
                    "after": current[r][c],
                }
                changes.append(item)
                if is_edge(r, c, rows, cols):
                    edge_changes.append(item)
                else:
                    interior_changes.append(item)

    replacements = {item["after"] for item in changes}
    uniform_edge = (
        bool(edge_changes)
        and not interior_changes
        and len(replacements) == 1
    )

    suspicious = (
        len(edge_changes) >= 3
        and not interior_changes
        and uniform_edge
    )

    if not changes:
        status = "UNCHANGED"
    elif suspicious:
        status = "SUSPICIOUS_EDGE_ONLY_CHANGE"
    elif interior_changes:
        status = "INTERIOR_CHANGE_REQUIRES_REVIEW"
    else:
        status = "EDGE_CHANGE_REQUIRES_REVIEW"

    return {
        "status": status,
        "changed_cells": len(changes),
        "edge_changes": len(edge_changes),
        "interior_changes": len(interior_changes),
        "uniform_edge_replacement": uniform_edge,
        "changes": changes,
        "transition_verified": False,
        "tile_removals_verified": False,
        "game_taps_enabled": False,
    }


def coordinate(image_path, baseline_path=BASELINE, capture_session_id=None):
    import screenshot_ingestor

    image_path = Path(image_path).expanduser().resolve()
    baseline_path = Path(baseline_path)

    if not image_path.is_file():
        raise FileNotFoundError(image_path)

    baseline_data = json.loads(baseline_path.read_text())
    extracted = extract_board(image_path, baseline_data)

    if extracted["grid_size"] != baseline_data["grid_size"]:
        raise ValueError("Screenshot grid does not match baseline")

    if extracted["bounds"] != baseline_data["bounds"]:
        raise ValueError("Screenshot calibration does not match baseline")

    transition = audit_transition(
        baseline_data["board"],
        extracted["board"],
    )

    digest = hashlib.sha256(image_path.read_bytes()).hexdigest()

    stat = image_path.stat()
    modified = datetime.fromtimestamp(
        stat.st_mtime, timezone.utc
    ).isoformat()

    from PIL import Image
    from capture_provenance import (
        parse_exif_capture_time,
        validate_capture_session_id,
    )
    with Image.open(image_path) as img:
        exif_time = parse_exif_capture_time(img.getexif())
    capture_session_id = validate_capture_session_id(capture_session_id)

    result = {
        "version": 1,
        "source_image": str(image_path),
        "source_sha256": digest,
        "snapshot_id": "sha256:" + digest,
        "board_snapshot_id": "sha256:" + digest,
        "captured_at": exif_time,
        "file_modified_at": modified,
        "timestamp_identified": bool(exif_time),
        "capture_session_id": capture_session_id,
        "board_dimensions": extracted["grid_size"],
        "transition": transition,
        "same_board_state_confirmed": False,
        "board_observation_available": True,
        "snapshot_synchronised": False,
        "identity_verified": False,
        "gameplay_verified": False,
        "game_taps_enabled": False,
        "actions_performed": False,
    }

    # Save the raw extraction as a candidate observation.
    # Never promote it to verified gameplay evidence.
    observation = {
        **extracted,
        "source": str(image_path),
        "source_sha256": digest,
        "snapshot_id": result["snapshot_id"],
        "board_snapshot_id": result["snapshot_id"],
        "captured_at": exif_time,
        "file_modified_at": modified,
        "timestamp_identified": bool(exif_time),
        "capture_session_id": capture_session_id,
        "same_board_state_confirmed": False,
        "gameplay_verified": False,
        "vision_classification_verified": False,
        "game_taps_enabled": False,
        "transition_status": transition["status"],
    }

    OBSERVATION.parent.mkdir(parents=True, exist_ok=True)
    REPORT.parent.mkdir(parents=True, exist_ok=True)

    for path, data in (
        (OBSERVATION, observation),
        (REPORT, result),
    ):
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(data, indent=2))
        temporary.replace(path)

    print("SLIME AI — BUILD 11K EVIDENCE COORDINATOR")
    print("=" * 52)
    print("Screenshot:", image_path.name)
    print("SHA256:", digest)
    print("EXIF capture time identified:", bool(exif_time))
    print("Transition:", transition["status"])
    print("Changed cells:", transition["changed_cells"])
    print("Edge changes:", transition["edge_changes"])
    print("Interior changes:", transition["interior_changes"])
    print("Board observation saved:", OBSERVATION)
    print("Coordinator report saved:", REPORT)
    print("Snapshot synchronised: False")
    print("Identity verified: False")
    print("Gameplay verified: False")
    print("Game taps enabled: False")
    print("Actions performed: False")

    return result


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("screenshot")
    parser.add_argument("--capture-session-id")
    args = parser.parse_args()
    coordinate(args.screenshot, capture_session_id=args.capture_session_id)
