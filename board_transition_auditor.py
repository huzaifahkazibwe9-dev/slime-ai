import json
from pathlib import Path

BASELINE = Path("data/vision_level39.json")
OBSERVED = Path("data/board_observation_latest.json")
OUTPUT = Path("data/board_transition_report.json")


def audit_transition(before, after):
    empty = {
        "valid": False,
        "errors": [],
        "removed": 0,
        "unchanged": 0,
        "added": 0,
        "recoloured": 0,
    }

    if not isinstance(before, list) or not isinstance(after, list):
        empty["errors"].append("Boards must be lists")
        return empty

    if not before or len(before) != len(after):
        empty["errors"].append("Board row counts differ or are empty")
        return empty

    if not all(isinstance(row, list) for row in before + after):
        empty["errors"].append("Every board row must be a list")
        return empty

    width = len(before[0])

    if width == 0 or any(
        len(row) != width for row in before + after
    ):
        empty["errors"].append("Boards must be rectangular")
        return empty

    removed = unchanged = added = recoloured = 0

    for r in range(len(before)):
        for c in range(width):
            old, new = before[r][c], after[r][c]

            if old is None and new is None:
                unchanged += 1
            elif old is not None and new is None:
                removed += 1
            elif old is None and new is not None:
                added += 1
            elif old == new:
                unchanged += 1
            else:
                recoloured += 1

    errors = []

    if added:
        errors.append("New occupied tiles appeared")

    if recoloured:
        errors.append("Existing tiles changed colour")

    return {
        "valid": not errors,
        "errors": errors,
        "rows": len(before),
        "columns": width,
        "removed": removed,
        "unchanged": unchanged,
        "added": added,
        "recoloured": recoloured,
        "before_occupied": sum(
            x is not None for row in before for x in row
        ),
        "after_occupied": sum(
            x is not None for row in after for x in row
        ),
    }


def main():
    baseline = json.loads(BASELINE.read_text())
    report = {
        "observed_board_available": OBSERVED.exists(),
        "planning_allowed": False,
        "game_taps_enabled": False,
    }

    if OBSERVED.exists():
        observed = json.loads(OBSERVED.read_text())
        result = audit_transition(
            baseline["board"], observed["board"]
        )
        report["transition"] = result
        report["status"] = (
            "STRUCTURALLY_VALID" if result["valid"]
            else "INVALID_TRANSITION"
        )
    else:
        report["transition"] = None
        report["status"] = "PENDING_OBSERVED_BOARD"

    OUTPUT.write_text(json.dumps(report, indent=2))

    print("SLIME AI — BOARD TRANSITION AUDITOR")
    print("=" * 48)
    print("Observed board available:", report["observed_board_available"])
    print("Status:", report["status"])

    if report["transition"]:
        for key in ("removed", "unchanged", "added", "recoloured"):
            print(f"{key.capitalize()}: {report['transition'][key]}")
        for error in report["transition"]["errors"]:
            print("ERROR:", error)

    print("Planning allowed:", report["planning_allowed"])
    print("Game taps enabled:", report["game_taps_enabled"])
    print("Report:", OUTPUT)


if __name__ == "__main__":
    main()
