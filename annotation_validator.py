"""Validator for human-reviewed shooter annotation packages.

Rejects any annotation that is incomplete or lacks explicit human confirmation.
Never generates or invents labels.
"""

import json
import re
from datetime import datetime, timezone
from pathlib import Path


SNAPSHOT_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


def _valid_session_id(value):
    return isinstance(value, str) and bool(value.strip()) and " " not in value


def _valid_timestamp(value):
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def validate_annotation(data):
    """Return (ok: bool, errors: list[str]).

    Accepts a dict (already parsed) or a path-like object.
    """
    errors = []
    if isinstance(data, (str, Path)):
        try:
            data = json.loads(Path(data).read_text())
        except (OSError, json.JSONDecodeError) as exc:
            return False, [f"failed to load annotation: {exc}"]

    if not isinstance(data, dict):
        return False, ["annotation must be a JSON object"]

    if data.get("annotation_version") != "1.0":
        errors.append("annotation_version must be '1.0'")

    if not _valid_session_id(data.get("capture_session_id")):
        errors.append("capture_session_id missing or invalid")

    snapshot = data.get("board_snapshot_id")
    if not isinstance(snapshot, str) or not SNAPSHOT_RE.fullmatch(snapshot):
        errors.append("board_snapshot_id missing or not a valid sha256 digest")

    if not _valid_timestamp(data.get("annotated_at")):
        errors.append("annotated_at missing or not an aware ISO-8601 timestamp")

    annotator = data.get("annotator")
    if not isinstance(annotator, str) or not annotator.strip():
        errors.append("annotator missing or empty")

    # Strict: only the boolean True is accepted.
    if data.get("human_confirmed") is not True:
        errors.append("human_confirmed must be exactly boolean true")

    shooters = data.get("shooters")
    if not isinstance(shooters, list):
        errors.append("shooters must be a list")
    else:
        seen_ids = set()
        for i, shooter in enumerate(shooters):
            if not isinstance(shooter, dict):
                errors.append(f"shooter[{i}] must be an object")
                continue
            shooter_id = shooter.get("id")
            if not isinstance(shooter_id, str) or not shooter_id.strip():
                errors.append(f"shooter[{i}].id missing or invalid")
            else:
                if shooter_id in seen_ids:
                    errors.append(f"shooter[{i}].id '{shooter_id}' is duplicated")
                seen_ids.add(shooter_id)
            if not isinstance(shooter.get("color"), str) or not shooter["color"].strip():
                errors.append(f"shooter[{i}].color missing or invalid")
            ammo = shooter.get("ammo")
            if type(ammo) is not int or ammo < 0:
                errors.append(f"shooter[{i}].ammo must be a non-negative integer")

            # Optional fields: validate only when present
            if "slot_index" in shooter:
                slot = shooter["slot_index"]
                if type(slot) is not int or not (0 <= slot <= 11):
                    errors.append(f"shooter[{i}].slot_index must be an integer in 0..11 when present")

            if "bonded_ids" in shooter:
                bonds = shooter["bonded_ids"]
                if not isinstance(bonds, list):
                    errors.append(f"shooter[{i}].bonded_ids must be a list when present")
                else:
                    for j, bond in enumerate(bonds):
                        if not isinstance(bond, str) or not bond.strip():
                            errors.append(f"shooter[{i}].bonded_ids[{j}] must be a non-empty string")
                        elif bond == shooter_id:
                            errors.append(f"shooter[{i}].bonded_ids must not contain self-reference '{bond}'")

        # After collecting all IDs, verify bonded references exist (if any)
        all_ids = {s.get("id") for s in shooters if isinstance(s, dict) and isinstance(s.get("id"), str)}
        for i, shooter in enumerate(shooters):
            if not isinstance(shooter, dict):
                continue
            bonds = shooter.get("bonded_ids")
            if isinstance(bonds, list):
                for bond in bonds:
                    if isinstance(bond, str) and bond not in all_ids:
                        errors.append(f"shooter[{i}].bonded_ids references unknown id '{bond}'")

    return len(errors) == 0, errors


def load_and_validate(path):
    """Convenience wrapper. Raises ValueError on failure."""
    ok, errors = validate_annotation(path)
    if not ok:
        raise ValueError("Invalid annotation:\n" + "\n".join(errors))
    return json.loads(Path(path).read_text())
