import hashlib
import json
import math
import re
from datetime import datetime
from pathlib import Path

from capture_provenance import validate_capture_session_id

DATA = Path("data")
ORDER = ["bottom", "right", "top", "left"]

def read_snapshot(name):
    """Parse one JSON object and hash the exact bytes that were parsed."""
    raw = (DATA / name).read_bytes()
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{name}: unreadable JSON payload") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{name}: top-level JSON value must be an object")
    return value, hashlib.sha256(raw).hexdigest()


def validate_visual_observations(observations, expected_positions):
    """Reject incomplete or ambiguous frame data before building tracks."""
    if not isinstance(observations, list):
        return ["Observations must be a list"]

    expected = set(expected_positions)
    seen = set()
    errors = []

    if len(observations) != len(expected):
        errors.append(
            f"Expected {len(expected)} observations; got {len(observations)}"
        )

    for index, item in enumerate(observations):
        if not isinstance(item, dict):
            errors.append(f"Observation {index} must be an object")
            continue

        position_id = item.get("position_id")
        if not isinstance(position_id, str) or not position_id.strip():
            errors.append(f"Observation {index} has invalid position_id")
            continue
        if position_id not in expected:
            errors.append(f"Unexpected position: {position_id}")
        if position_id in seen:
            errors.append(f"Duplicate position: {position_id}")
        seen.add(position_id)

        colour = item.get("colour")
        if not isinstance(colour, str) or colour.lower() not in {
            "white", "blue", "cyan"
        }:
            errors.append(f"{position_id}: invalid colour")

        ammo = item.get("ammo")
        if type(ammo) is not int or ammo < 0:
            errors.append(f"{position_id}: invalid ammunition")

    missing = sorted(expected - seen)
    if missing:
        errors.append("Missing positions: " + ", ".join(missing))
    return errors


def validate_visual_provenance(visual):
    """Require explicit identity-frame linkage to a board capture session."""
    if not isinstance(visual, dict):
        return ["Visual observation artifact must be an object"]
    errors = []
    snapshot_id = visual.get("board_snapshot_id")
    if not isinstance(snapshot_id, str) or not re.fullmatch(
        r"sha256:[0-9a-f]{64}", snapshot_id
    ):
        errors.append("Missing or invalid board_snapshot_id")
    try:
        validate_capture_session_id(visual.get("capture_session_id"))
    except ValueError:
        errors.append("Missing or invalid capture_session_id")
    if visual.get("capture_session_id") is None:
        errors.append("Missing or invalid capture_session_id")
    captured_at = visual.get("captured_at")
    if not isinstance(captured_at, str) or not captured_at.strip():
        errors.append("Missing capture timestamp")
    else:
        try:
            parsed = datetime.fromisoformat(captured_at.replace("Z", "+00:00"))
            if parsed.tzinfo is None or parsed.utcoffset() is None:
                errors.append("Capture timestamp must include a UTC offset")
        except ValueError:
            errors.append("Capture timestamp is invalid")
    if visual.get("timestamp_identified") is not True:
        errors.append("Capture timestamp is not explicitly identified")
    return errors


def validate_observation_provenance(observations, visual):
    """Reject per-observation metadata that conflicts with the parent capture."""
    if not isinstance(observations, list) or not isinstance(visual, dict):
        return ["Observation provenance requires a list and capture object"]

    errors = []
    fields = (
        "board_snapshot_id",
        "capture_session_id",
        "captured_at",
        "timestamp_identified",
    )
    for index, item in enumerate(observations):
        if not isinstance(item, dict):
            continue
        for field in fields:
            if field in item and item.get(field) != visual.get(field):
                errors.append(
                    f"Observation {index}: {field} conflicts with parent capture"
                )
    return errors


def read_optional_snapshot(name):
    """Read an optional JSON object from one immutable byte snapshot."""
    try:
        return read_snapshot(name)
    except FileNotFoundError:
        return {}, None


def validate_identity_audit(identity, board, visual, expected_positions,
                             expected_source_file_sha256):
    """Require a current, user-confirmed identity map bound to exact inputs."""
    errors = []
    if not isinstance(identity, dict):
        return ["Identity audit report is missing or malformed"], {}
    if not isinstance(board, dict) or not isinstance(visual, dict):
        return ["Board and conveyor visual artifacts must be JSON objects"], {}

    if identity.get("identity_verified") is not True:
        errors.append("Human-confirmed identity audit is not verified")
    if identity.get("errors") != [] or identity.get("blockers") != []:
        errors.append("Identity audit contains errors or blockers")
    if identity.get("board_snapshot_id") != board.get("snapshot_id"):
        errors.append("Identity audit does not match the current board snapshot")
    if identity.get("capture_session_id") != board.get("capture_session_id"):
        errors.append("Identity audit does not match the current capture session")
    if identity.get("board_snapshot_id") != visual.get("board_snapshot_id"):
        errors.append("Identity audit and conveyor observations use different board snapshots")
    if identity.get("capture_session_id") != visual.get("capture_session_id"):
        errors.append("Identity audit and conveyor observations use different capture sessions")
    if (
        identity.get("timestamp_identified") is not True
        or identity.get("timestamps_known") is not True
    ):
        errors.append("Identity audit timestamps are not fully identified")

    identity_time = identity.get("captured_at")
    board_time = board.get("captured_at")
    visual_time = visual.get("captured_at")
    try:
        identity_dt = datetime.fromisoformat(
            identity_time.replace("Z", "+00:00")
        )
        board_dt = datetime.fromisoformat(board_time.replace("Z", "+00:00"))
        visual_dt = datetime.fromisoformat(visual_time.replace("Z", "+00:00"))
        if any(
            value.tzinfo is None or value.utcoffset() is None
            for value in (identity_dt, board_dt, visual_dt)
        ):
            raise ValueError("naive timestamp")
        if abs((identity_dt - board_dt).total_seconds()) > 120:
            errors.append("Identity audit timestamp is not aligned with board capture")
        if abs((visual_dt - board_dt).total_seconds()) > 120:
            errors.append("Conveyor visual timestamp is not aligned with board capture")
    except (AttributeError, TypeError, ValueError):
        errors.append("Identity, board, and visual timestamps must all be timezone-aware")

    positions_checked = identity.get("positions_checked")
    if (
        type(positions_checked) is not int
        or positions_checked < 1
        or positions_checked > len(expected_positions)
    ):
        errors.append("Identity audit current-shooter count is invalid")
    if identity.get("verified_by_user") is not True:
        errors.append("Identity audit lacks explicit user confirmation")

    expected_sources = {
        "board_observation_json": expected_source_file_sha256.get(
            "board_observation_json"
        ),
        "conveyor_visual_observations_json": expected_source_file_sha256.get(
            "conveyor_visual_observations_json"
        ),
        "shooter_identity_observations_json": expected_source_file_sha256.get(
            "shooter_identity_observations_json"
        ),
        "conveyor_calibration_json": expected_source_file_sha256.get(
            "conveyor_calibration_json"
        ),
        "shooter_detection_json": expected_source_file_sha256.get(
            "shooter_detection_json"
        ),
    }
    if (
        not isinstance(identity.get("source_file_sha256"), dict)
        or identity.get("source_file_sha256") != expected_sources
        or any(
            not isinstance(value, str)
            or re.fullmatch(r"[0-9a-f]{64}", value) is None
            for value in expected_sources.values()
        )
    ):
        errors.append("Identity audit source fingerprints do not match current input files")

    known = identity.get("known_shooters")
    if (
        not isinstance(known, list)
        or not known
        or any(not isinstance(value, str) or not value for value in known)
        or len(set(known)) != len(known)
    ):
        errors.append("Identity audit known_shooters list is invalid")
        known = []

    shooter_positions = identity.get("shooter_positions")
    if not isinstance(shooter_positions, dict):
        errors.append("Identity audit shooter_positions map is missing")
        shooter_positions = {}
    for shooter_id, positions in shooter_positions.items():
        if (
            shooter_id not in known
            or not isinstance(positions, list)
            or any(position not in expected_positions for position in positions)
            or len(set(positions)) != len(positions)
        ):
            errors.append(f"Identity audit has an invalid historical track for {shooter_id}")

    current_positions = identity.get("current_position_by_shooter")
    if not isinstance(current_positions, dict):
        errors.append("Identity audit current-position map is missing")
        current_positions = {}
    current_values = list(current_positions.values())
    historical_positions = {
        position
        for known_positions in shooter_positions.values()
        if isinstance(known_positions, list)
        for position in known_positions
    }
    if historical_positions != expected_positions:
        errors.append(
            "Identity audit history does not cover every calibrated conveyor position"
        )
    if (
        set(current_positions) != set(known)
        or len(current_positions) != positions_checked
        or any(position not in expected_positions for position in current_values)
        or len(set(current_values)) != len(current_values)
    ):
        errors.append(
            "Identity audit current frame must map every detected shooter to one distinct calibrated position"
        )

    return sorted(set(errors)), shooter_positions


def validate_calibration_positions(positions):
    """Validate unique calibration records and finite geometry coordinates."""
    errors = []
    if isinstance(positions, list):
        if not positions:
            return ["Calibration shooter list must be non-empty"]
        normalized = {}
        for index, item in enumerate(positions):
            if not isinstance(item, dict):
                errors.append(f"Calibration record {index} must be an object")
                continue
            position_id = item.get("id")
            if not isinstance(position_id, str) or not position_id.strip():
                errors.append(f"Calibration record {index} has an invalid ID")
                continue
            if position_id in normalized:
                errors.append(f"Duplicate calibrated position ID: {position_id}")
                continue
            normalized[position_id] = item
        positions = normalized
    if not isinstance(positions, dict) or not positions:
        return errors + ["Calibration positions must be a non-empty object map"]

    for position_id, position in positions.items():
        if not isinstance(position_id, str) or not position_id.strip():
            errors.append("Calibration position ID must be a non-empty string")
            continue
        if not isinstance(position, dict):
            errors.append(f"{position_id}: calibration entry must be an object")
            continue
        if position.get("segment") not in ORDER:
            errors.append(f"{position_id}: invalid conveyor segment")
        center = position.get("center")
        if (
            not isinstance(center, list)
            or len(center) != 2
            or any(
                type(value) not in (int, float)
                or (type(value) is float and not math.isfinite(value))
                for value in center
            )
        ):
            errors.append(f"{position_id}: center must contain two finite coordinates")
    return errors


def validate_required_position_layout(positions):
    """Require the eight calibrated positions expected by the four-side matcher."""
    expected = {
        f"{side}_{slot}"
        for side in ORDER
        for slot in (1, 2)
    }
    if not isinstance(positions, dict):
        return ["Calibration positions must be an object map"]
    actual = set(positions)
    if actual != expected:
        missing = sorted(expected - actual)
        unexpected = sorted(actual - expected)
        errors = []
        if missing:
            errors.append("Missing required conveyor positions: " + ", ".join(missing))
        if unexpected:
            errors.append("Unexpected conveyor positions: " + ", ".join(unexpected))
        return errors
    errors = []
    for position_id, position in positions.items():
        expected_segment = position_id.split("_", 1)[0]
        if (
            not isinstance(position, dict)
            or position.get("segment") != expected_segment
        ):
            errors.append(
                f"{position_id}: calibrated segment does not match its position ID"
            )
    return errors


def derive_candidate_track(
    name, specification, shooter_positions, current_position_by_shooter,
    shooters, calibrated_positions, observations_by_position, visual,
):
    """Derive one candidate identity from human-confirmed historical tracks."""
    track_positions = specification["positions"]
    possible_shooters = None
    for position_id in track_positions:
        candidates_at_position = {
            shooter_id
            for shooter_id, known_positions in shooter_positions.items()
            if isinstance(known_positions, list) and position_id in known_positions
        }
        possible_shooters = (
            candidates_at_position if possible_shooters is None
            else possible_shooters.intersection(candidates_at_position)
        )
    candidate_shooter = (
        next(iter(possible_shooters))
        if possible_shooters and len(possible_shooters) == 1
        else None
    )
    current_position_id = (
        current_position_by_shooter.get(candidate_shooter)
        if candidate_shooter else None
    )
    shooter = (
        shooters.get(candidate_shooter)
        if candidate_shooter is not None else None
    )
    panel_colour = (
        shooter.get("color", {}).get("name")
        if isinstance(shooter, dict)
        and isinstance(shooter.get("color"), dict)
        else None
    )

    records = []
    for position_id in track_positions:
        observation = observations_by_position[position_id]
        position = calibrated_positions[position_id]
        records.append({
            "position_id": position_id,
            "segment": position.get("segment"),
            "colour": observation["colour"],
            "ammo": observation["ammo"],
            "center": position.get("center"),
            "board_snapshot_id": visual.get("board_snapshot_id"),
            "capture_session_id": visual.get("capture_session_id"),
            "captured_at": visual.get("captured_at"),
            "timestamp_identified": visual.get("timestamp_identified") is True,
        })

    ammo = [record["ammo"] for record in records]
    ammo_non_increasing = all(
        later <= earlier for earlier, later in zip(ammo, ammo[1:])
    )
    panel_colour_match = panel_colour in specification["allowed_panel_colours"]
    observed_colours_match = all(
        (
            record["colour"].lower() == "white"
            if name == "white"
            else record["colour"].lower() in {"blue", "cyan"}
        )
        for record in records
    )
    return {
        "candidate_shooter": candidate_shooter,
        "current_position_id": current_position_id,
        "board_snapshot_id": visual.get("board_snapshot_id"),
        "capture_session_id": visual.get("capture_session_id"),
        "captured_at": visual.get("captured_at"),
        "timestamp_identified": visual.get("timestamp_identified") is True,
        "panel_colour": panel_colour,
        "observations": records,
        "ammo_non_increasing": ammo_non_increasing,
        "panel_colour_match": panel_colour_match,
        "observed_colour_consistent": observed_colours_match,
        "candidate_supported": (
            candidate_shooter is not None
            and current_position_id in track_positions
            and ammo_non_increasing
            and panel_colour_match
            and observed_colours_match
        ),
    }


def main():
    input_errors = []

    def read_required(name):
        try:
            return read_snapshot(name)
        except (OSError, ValueError) as exc:
            input_errors.append(f"{name}: {type(exc).__name__}: {exc}")
            return {}, None

    calibration, calibration_digest = read_required("conveyor_calibration.json")
    visual, visual_digest = read_required("conveyor_visual_observations.json")
    detection, detection_digest = read_required("shooter_detection.json")
    identity_report, identity_digest = read_required("identity_audit_report.json")
    board, board_digest = read_required("board_observation_latest.json")
    _, identity_observations_digest = read_required(
        "shooter_identity_observations.json"
    )
    source_file_sha256 = {
        "conveyor_calibration_json": calibration_digest,
        "conveyor_visual_observations_json": visual_digest,
        "shooter_detection_json": detection_digest,
        "identity_audit_json": identity_digest,
        "board_observation_json": board_digest,
        "shooter_identity_observations_json": identity_observations_digest,
    }

    observations = visual.get("observations", [])
    raw_positions = calibration.get("shooters", [])
    raw_shooters = detection.get("visible_shooters", [])
    calibration_errors = validate_calibration_positions(raw_positions)
    positions = {
        item["id"]: item for item in raw_positions
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    } if isinstance(raw_positions, list) else {}
    calibration_errors.extend(validate_required_position_layout(positions))
    shooters = {
        item["id"]: item for item in raw_shooters
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }

    validation_errors = list(input_errors)
    validation_errors.extend(calibration_errors)
    validation_errors.extend(validate_visual_observations(
        observations, positions
    ))
    validation_errors.extend(validate_visual_provenance(visual))
    validation_errors.extend(
        validate_observation_provenance(observations, visual)
    )
    identity_errors, shooter_positions = validate_identity_audit(
        identity_report,
        board,
        visual,
        set(positions),
        {
            "board_observation_json": board_digest,
            "conveyor_visual_observations_json": visual_digest,
            "shooter_identity_observations_json": identity_observations_digest,
            "conveyor_calibration_json": calibration_digest,
            "shooter_detection_json": detection_digest,
        },
    )
    validation_errors.extend(identity_errors)
    identity_verified = not identity_errors

    by_position = {
        item["position_id"]: item
        for item in observations
        if isinstance(item, dict) and isinstance(item.get("position_id"), str)
    }
    track_specs = {
        "white": {
            "positions": ["bottom_1", "right_2", "top_2", "left_1"],
            "allowed_panel_colours": {"white"},
        },
        "blue_cyan": {
            "positions": ["bottom_2", "right_1", "top_1", "left_2"],
            "allowed_panel_colours": {"blue", "cyan"},
        },
    }

    if validation_errors:
        report = {
            "screenshot_order": ORDER,
            "board_snapshot_id": visual.get("board_snapshot_id"),
            "capture_session_id": visual.get("capture_session_id"),
            "captured_at": visual.get("captured_at"),
            "timestamp_identified": visual.get("timestamp_identified") is True,
            "observations_valid": not bool(
                validate_visual_observations(observations, positions)
            ),
            "validation_errors": sorted(set(validation_errors)),
            "tracks": {},
            "source_file_sha256": source_file_sha256,
            "checks": {
                "observations_valid": not bool(
                    validate_visual_observations(observations, positions)
                ),
                "identity_previously_verified": identity_verified,
            },
            "candidate_provenance_verified": False,
            "identity_verified": identity_verified,
            "gameplay_verified": False,
            "game_taps_enabled": False,
            "actions_performed": False,
            "note": "Candidate matching skipped because identity or capture provenance is incomplete.",
        }
        output = DATA / "conveyor_identity_candidates.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_suffix(output.suffix + ".tmp")
        temporary.write_text(json.dumps(report, indent=2))
        temporary.replace(output)
        print("Candidate matching blocked:")
        for error in report["validation_errors"]:
            print("-", error)
        print("Candidate report:", output)
        print("Identity verified:", report["identity_verified"])
        print("Gameplay taps enabled: False")
        return report

    report = {
        "screenshot_order": ORDER,
        "board_snapshot_id": visual.get("board_snapshot_id"),
        "capture_session_id": visual.get("capture_session_id"),
        "captured_at": visual.get("captured_at"),
        "timestamp_identified": visual.get("timestamp_identified") is True,
        "tracks": {},
        "source_file_sha256": source_file_sha256,
        "checks": {},
        "identity_verified": identity_verified,
        "gameplay_verified": False,
        "gameplay_taps_enabled": False,
        "game_taps_enabled": False,
        "actions_performed": False,
        "note": (
            "Human-confirmed physical identity only; colour interpretation, "
            "ammunition OCR, and gameplay remain unverified."
        ),
    }

    validation_errors.extend(validate_calibration_positions(positions))
    if validation_errors:
        report["validation_errors"] = sorted(set(validation_errors))
        report["checks"]["calibration_geometry_valid"] = False
        output = DATA / "conveyor_identity_candidates.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_suffix(output.suffix + ".tmp")
        temporary.write_text(json.dumps(report, indent=2))
        temporary.replace(output)
        print("Candidate matching blocked by calibration geometry.")
        for error in report["validation_errors"]:
            print("-", error)
        print("Identity verified:", identity_verified)
        print("Gameplay taps enabled: False")
        return report

    for name, specification in track_specs.items():
        report["tracks"][name] = derive_candidate_track(
            name,
            specification,
            shooter_positions,
            identity_report.get("current_position_by_shooter", {}),
            shooters,
            positions,
            by_position,
            visual,
        )

    candidate_pair = [
        track["candidate_shooter"]
        for track in report["tracks"].values()
    ]
    candidate_pair_valid = (
        len(candidate_pair) == 2
        and all(isinstance(value, str) and value in shooters for value in candidate_pair)
        and len(set(candidate_pair)) == 2
    )
    bonded_pair_confirmed = False
    if candidate_pair_valid:
        first, second = candidate_pair
        first_bonds = shooters[first].get("bonded_ids", [])
        second_bonds = shooters[second].get("bonded_ids", [])
        bonded_pair_confirmed = (
            isinstance(first_bonds, list)
            and isinstance(second_bonds, list)
            and second in first_bonds
            and first in second_bonds
        )

    observed_order = [
        by_position[f"{side}_1"]["position_id"].split("_")[0]
        for side in ORDER
    ]
    report["checks"] = {
        "four_sides_in_expected_order": observed_order == ORDER,
        "eight_observations_present": len(observations) == 8,
        "two_candidate_tracks_supported": all(
            track["candidate_supported"] for track in report["tracks"].values()
        ),
        "candidate_pair_is_user_confirmed_bond": bonded_pair_confirmed,
        "timestamps_known": (
            visual.get("timestamp_identified") is True
            and bool(visual.get("captured_at"))
        ),
        "snapshot_linked": (
            visual.get("board_snapshot_id") == board.get("snapshot_id")
        ),
        "current_snapshot_identified": (
            isinstance(board.get("snapshot_id"), str)
            and re.fullmatch(r"sha256:[0-9a-f]{64}", board["snapshot_id"]) is not None
            and visual.get("board_snapshot_id") == board.get("snapshot_id")
            and identity_report.get("board_snapshot_id") == board.get("snapshot_id")
        ),
        "capture_session_linked": (
            visual.get("capture_session_id") == board.get("capture_session_id")
        ),
        "identity_previously_verified": identity_verified,
        "identity_sources_match_current_inputs": identity_verified,
    }
    report["candidate_pair"] = candidate_pair if candidate_pair_valid else []
    report["current_snapshot_id"] = (
        board.get("snapshot_id") if candidate_pair_valid else None
    )
    report["candidate_provenance_verified"] = (
        identity_verified
        and all(
            track.get("board_snapshot_id") == visual.get("board_snapshot_id")
            and track.get("capture_session_id") == visual.get("capture_session_id")
            and track.get("captured_at") == visual.get("captured_at")
            and all(
                record.get("board_snapshot_id") == visual.get("board_snapshot_id")
                and record.get("capture_session_id") == visual.get("capture_session_id")
                and record.get("captured_at") == visual.get("captured_at")
                and record.get("timestamp_identified") is True
                for record in track.get("observations", [])
            )
            for track in report["tracks"].values()
        )
    )
    report["identity_verified"] = identity_verified

    output = DATA / "conveyor_identity_candidates.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(json.dumps(report, indent=2))
    temporary.replace(output)

    print("=" * 52)
    print("SLIME AI — CONVEYOR IDENTITY MATCHER")
    print("=" * 52)
    for name, track in report["tracks"].items():
        print(f"\\n{name.upper()} TRACK")
        print("Candidate:", track["candidate_shooter"])
        print("Current position:", track["current_position_id"])
        print("Ammo:", [record["ammo"] for record in track["observations"]])
        print("Candidate supported:", track["candidate_supported"])
    print("\\nCHECKS")
    for name, passed in report["checks"].items():
        print(f"[{'PASS' if passed else 'PENDING'}] {name}")
    print("\\nIdentity verified:", report["identity_verified"])
    print("Candidate provenance verified:", report["candidate_provenance_verified"])
    print("Gameplay verified: False")
    print("Gameplay taps enabled: False")
    print("Report:", output)
    print("No game actions performed.")
    return report


if __name__ == "__main__":
    main()
