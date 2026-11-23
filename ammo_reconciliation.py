"""Conservative ammunition evidence and simulation reconciliation.

This module never upgrades screenshot data to verified evidence. A human-
confirmed observation must carry explicit provenance, and simulated shot
consumption is checked independently from observed ammo.
"""


def _valid_count(value):
    return type(value) is int and value >= 0


def validate_ammo_observation(position_id, ammo, observations):
    """Validate one conveyor ammo reading against its capture provenance."""
    if not isinstance(observations, dict):
        observations = {}

    capture_id = observations.get("capture_session_id")
    snapshot_id = observations.get("board_snapshot_id")
    timestamp = observations.get("observed_at")
    confirmed = observations.get("ammo_verified_by_user") is True

    checks = {
        "ammo_is_non_negative_integer": _valid_count(ammo),
        "position_identity_matches": (
            observations.get("position_id") == position_id
        ),
        "capture_session_present": (
            isinstance(capture_id, str) and bool(capture_id.strip())
        ),
        "board_snapshot_present": (
            isinstance(snapshot_id, str) and bool(snapshot_id.strip())
        ),
        "observation_timestamp_present": (
            isinstance(timestamp, str) and bool(timestamp.strip())
        ),
        "explicit_user_confirmation": confirmed,
    }
    return {
        "position_id": position_id,
        "ammo": ammo if _valid_count(ammo) else None,
        "capture_session_id": capture_id,
        "board_snapshot_id": snapshot_id,
        "observed_at": timestamp,
        "checks": checks,
        "verified": all(checks.values()),
        "source": "conveyor_visual_observation",
    }


def reconcile_simulated_ammo(initial_ammo, shots_used, reported_remaining):
    """Check conservation of ammo across a hypothetical simulation."""
    valid = (
        _valid_count(initial_ammo)
        and _valid_count(shots_used)
        and _valid_count(reported_remaining)
    )
    if not valid:
        return {
            "consistent": False,
            "status": "INVALID_AMMUNITION_COUNTS",
            "expected_remaining": None,
        }

    expected = initial_ammo - shots_used
    consistent = expected >= 0 and reported_remaining == expected
    return {
        "consistent": consistent,
        "status": "RECONCILED" if consistent else "AMMUNITION_DELTA_MISMATCH",
        "expected_remaining": max(0, expected),
    }
