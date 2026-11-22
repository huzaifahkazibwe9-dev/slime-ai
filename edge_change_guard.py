def inspect_edge_changes(previous, current):
    if not previous or not current:
        raise ValueError("Boards cannot be empty")

    if len(previous) != len(current):
        raise ValueError("Board row counts differ")

    rows = len(previous)
    cols = len(previous[0])

    if cols == 0:
        raise ValueError("Board cannot have empty rows")

    if any(len(row) != cols for row in previous + current):
        raise ValueError("Boards must be rectangular")

    changes = []

    for r in range(rows):
        for c in range(cols):
            old = previous[r][c]
            new = current[r][c]

            if old != new:
                edge = r in (0, rows - 1) or c in (0, cols - 1)
                changes.append({
                    "row": r,
                    "column": c,
                    "previous": old,
                    "current": new,
                    "edge": edge,
                })

    edge_changes = [item for item in changes if item["edge"]]
    interior_changes = [item for item in changes if not item["edge"]]

    replacement_counts = {}
    for item in edge_changes:
        colour = item["current"]
        replacement_counts[colour] = replacement_counts.get(colour, 0) + 1

    uniform_edge_replacement = (
        bool(edge_changes)
        and len(replacement_counts) == 1
    )

    suspicious = (
        len(changes) >= 3
        and len(interior_changes) == 0
        and uniform_edge_replacement
    )

    if not changes:
        status = "UNCHANGED"
    elif suspicious:
        status = "SUSPICIOUS_EDGE_ONLY_CHANGE"
    elif interior_changes:
        status = "INTERIOR_CHANGE_REQUIRES_VALIDATION"
    else:
        status = "EDGE_CHANGE_REQUIRES_VALIDATION"

    return {
        "status": status,
        "changed_cells": len(changes),
        "edge_changes": len(edge_changes),
        "interior_changes": len(interior_changes),
        "uniform_edge_replacement": uniform_edge_replacement,
        "replacement_counts": replacement_counts,
        "changes": changes,
        "board_transition_verified": False,
        "game_taps_enabled": False,
    }
