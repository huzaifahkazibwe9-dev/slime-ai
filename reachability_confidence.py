import argparse
import hashlib
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




def observation_confidence(board):
    """Return provisional labels for screenshot cells; no cell is confirmed."""
    if not isinstance(board, list) or not board:
        raise ValueError("Board must be a non-empty list")
    height = len(board)
    width = len(board[0]) if isinstance(board[0], list) else 0
    if width < 1 or any(
        not isinstance(row, list) or len(row) != width for row in board
    ):
        raise ValueError("Board must be rectangular")
    return [
        [
            "requires_confirmation"
            if row in (0, height - 1) or col in (0, width - 1)
            else "provisional"
            for col in range(width)
        ]
        for row in range(height)
    ]


def validate_board_observation_source(report, board_sha256):
    """Require confidence analysis to use the exact board bytes traced upstream."""
    if not isinstance(report, dict):
        raise ValueError("Reachability report must be a JSON object")
    provenance = report.get("source_file_sha256")
    if (
        not isinstance(provenance, dict)
        or provenance.get("board_json") != board_sha256
    ):
        raise ValueError(
            "Board observation bytes do not match the reachability audit source"
        )
    return True

def validate_edge_confidence_source(confidence_data, board_sha256):
    """Require the edge-confidence report to derive from this exact board file."""
    if not isinstance(confidence_data, dict):
        raise ValueError("Invalid confidence report")
    provenance = confidence_data.get("source_file_sha256")
    if (not isinstance(provenance, dict)
            or provenance.get("vision_level39_json") != board_sha256):
        raise ValueError(
            "Edge-confidence report does not match the exact board source bytes"
        )
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Annotate reachability lanes with conservative board confidence"
    )
    parser.add_argument("--input", default=str(INPUT_FILE))
    parser.add_argument("--board", help="Optional screenshot-ingestor observation JSON")
    parser.add_argument("--output", default=str(OUTPUT_FILE))
    args = parser.parse_args()

    report_bytes = Path(args.input).read_bytes()
    report = json.loads(report_bytes)
    source_hashes = {
        "reachability_audit_json": hashlib.sha256(report_bytes).hexdigest(),
    }
    confidence_snapshot_id = None
    confidence_snapshot_match_verified = False
    if args.board:
        board_bytes = Path(args.board).read_bytes()
        source = json.loads(board_bytes)
        board_digest = hashlib.sha256(board_bytes).hexdigest()
        from screenshot_observation_loader import _require_grid
        _require_grid(source)
        source_snapshot_id = source.get("snapshot_id")
        report_snapshot_id = report.get("board_snapshot_id")
        if (
            not isinstance(source_snapshot_id, str)
            or not source_snapshot_id
            or not isinstance(report_snapshot_id, str)
            or not report_snapshot_id
            or source_snapshot_id != report_snapshot_id
        ):
            raise ValueError(
                "Confidence screenshot snapshot does not match reachability audit"
            )
        validate_board_observation_source(report, board_digest)
        source_hashes["board_observation_json"] = board_digest
        confidence_matrix = observation_confidence(source["board"])
        confidence_snapshot_id = source_snapshot_id
        confidence_snapshot_match_verified = True
    else:
        from board_loader import VISION_FILE, CONFIDENCE_FILE
        board_bytes = Path(VISION_FILE).read_bytes()
        confidence_bytes = Path(CONFIDENCE_FILE).read_bytes()
        board_source = json.loads(board_bytes)
        confidence_source = json.loads(confidence_bytes)
        board_digest = hashlib.sha256(board_bytes).hexdigest()
        validate_board_observation_source(report, board_digest)
        validate_edge_confidence_source(confidence_source, board_digest)
        board_data = load_board(
            data=board_source,
            confidence_data=confidence_source,
        )
        source_hashes["vision_level39_json"] = board_digest
        source_hashes["edge_confidence_json"] = hashlib.sha256(confidence_bytes).hexdigest()
        confidence_matrix = board_data.get("confidence")

    if confidence_matrix is None:
        raise ValueError("No board confidence data is available")

    upstream_source_file_sha256 = report.get("source_file_sha256")
    upstream_source_kind = report.get("board_source_kind")
    report = annotate_report(report, confidence_matrix)
    report["upstream_source_file_sha256"] = (
        dict(upstream_source_file_sha256)
        if isinstance(upstream_source_file_sha256, dict) else None
    )
    report["upstream_source_kind"] = upstream_source_kind
    report["source_file_sha256"] = source_hashes
    report["confidence_audit"]["source_snapshot_id"] = confidence_snapshot_id
    report["confidence_audit"]["snapshot_match_verified"] = (
        confidence_snapshot_match_verified
        and confidence_snapshot_id == report.get("board_snapshot_id")
    )
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2))

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
    print("Report:", output_path)


if __name__ == "__main__":
    main()
