import json
from pathlib import Path

from board_loader import load_board

INPUT_FILE = Path("data/reachability_audit.json")
OUTPUT_FILE = Path("data/reachability_confidence_latest.json")


def confidence_status(cell):
    """Read a confidence label without guessing when its format is unknown."""
    if isinstance(cell, str):
        return cell
    if isinstance(cell, dict):
        for key in ("status", "confidence_status", "confidence", "classification"):
            value = cell.get(key)
            if isinstance(value, str) and value:
                return value
    return "unknown"


def annotate_report(report, confidence_matrix):
    if not isinstance(confidence_matrix, list) or not confidence_matrix:
        raise ValueError("Confidence matrix must be a non-empty list")

    height = len(confidence_matrix)
    width = len(confidence_matrix[0])

    if width == 0 or any(
        not isinstance(row, list) or len(row) != width
        for row in confidence_matrix
    ):
        raise ValueError("Confidence matrix must be rectangular")

    board_dimensions = report.get("board_dimensions")
    if board_dimensions != [width, height]:
        raise ValueError(
            "Confidence matrix dimensions do not match reachability report"
        )

    board_counts = {}
    for row in confidence_matrix:
        for cell in row:
            status = confidence_status(cell)
            board_counts[status] = board_counts.get(status, 0) + 1

    annotated_scenarios = 0
    confirmed_scenarios = 0
    uncertain_scenarios = 0

    for position in report.get("results", []):
        for scenario in position.get("scenarios", []):
            lane_cells = scenario.get("lane_cells", [])
            statuses = []

            for lane_cell in lane_cells:
                row = lane_cell.get("row")
                column = lane_cell.get("column")

                if (
                    not isinstance(row, int)
                    or not isinstance(column, int)
                    or not (0 <= row < height and 0 <= column < width)
                ):
                    status = "unknown"
                else:
                    status = confidence_status(
                        confidence_matrix[row][column]
                    )

                lane_cell["confidence_status"] = status
                statuses.append(status)

            all_confirmed = bool(statuses) and all(
                status == "confirmed" for status in statuses
            )

            scenario["confidence_cell_counts"] = {
                status: statuses.count(status)
                for status in sorted(set(statuses))
            }
            scenario["confidence_eligible"] = all_confirmed

            # Existing eligibility is retained but can never be upgraded here.
            scenario["planning_eligible"] = (
                bool(scenario.get("planning_eligible", False))
                and all_confirmed
            )

            annotated_scenarios += 1
            if all_confirmed:
                confirmed_scenarios += 1
            else:
                uncertain_scenarios += 1

    report["confidence_audit"] = {
        "source": "board_loader.load_board confidence matrix",
        "board_cell_counts": board_counts,
        "annotated_scenarios": annotated_scenarios,
        "confirmed_scenarios": confirmed_scenarios,
        "uncertain_scenarios": uncertain_scenarios,
        "all_lane_cells_confirmed": (
            annotated_scenarios > 0
            and confirmed_scenarios == annotated_scenarios
        ),
        "confidence_verification_enabled": False,
        "gameplay_verified": False,
        "game_taps_enabled": False,
    }

    return report


def main():
    report = json.loads(INPUT_FILE.read_text())
    board_data = load_board()
    confidence_matrix = board_data.get("confidence")

    if confidence_matrix is None:
        raise ValueError("Board loader did not provide confidence data")

    report = annotate_report(report, confidence_matrix)
    OUTPUT_FILE.write_text(json.dumps(report, indent=2))

    audit = report["confidence_audit"]
    print("SLIME AI — BUILD 11G CONFIDENCE REACHABILITY")
    print("=" * 52)
    print("Board dimensions:", report["board_dimensions"])
    print("Board confidence counts:", audit["board_cell_counts"])
    print("Scenarios annotated:", audit["annotated_scenarios"])
    print("Confirmed scenarios:", audit["confirmed_scenarios"])
    print("Uncertain scenarios:", audit["uncertain_scenarios"])
    print("All lane cells confirmed:", audit["all_lane_cells_confirmed"])
    print("Gameplay verified:", audit["gameplay_verified"])
    print("Game taps enabled:", audit["game_taps_enabled"])
    print("Report:", OUTPUT_FILE)


if __name__ == "__main__":
    main()
