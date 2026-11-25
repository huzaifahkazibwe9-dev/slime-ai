"""Evidence-aware, plan-only controller for Slime AI.

The controller never performs Android touch injection. It delegates planning
to the evidence-gated orchestration pipeline and reports whether a candidate
exists without treating a dry-run result as gameplay authorization.
"""
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
REPORT = DATA_DIR / "orchestration_latest.json"


class SlimeController:
    def __init__(self, data_dir=None):
        self.data_dir = Path(data_dir) if data_dir else DATA_DIR
        self.report_path = self.data_dir / "orchestration_latest.json"
        self.paused = False
        self.tap_enabled = False
        self.last_plan = None

    def readiness(self):
        try:
            value = json.loads(self.report_path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def status(self):
        report = self.readiness()
        evidence = report.get("evidence", {})
        planner = report.get("planner", {})
        evidence_gate_passed = (
            isinstance(evidence, dict)
            and evidence.get("evidence_gate_passed") is True
        )
        capture_evidence_valid = False
        capture_report_matches = False
        board_calibration_matches = False
        observation = self.data_dir / "board_observation_latest.json"
        shooters = self.data_dir / "shooter_detection.json"
        if observation.is_file() and shooters.is_file():
            try:
                from capture_preflight import validate_capture_pair
                from orchestration import _read_capture_bundle
                pinned = _read_capture_bundle(observation, shooters)
                capture = validate_capture_pair(
                    observation,
                    shooters,
                    board_data=pinned["board_data"],
                    shooter_data=pinned["shooter_data"],
                    pixel_audit_data=pinned["pixel_audit_data"],
                )
                capture_evidence_valid = capture.get("valid") is True
                if capture_evidence_valid:
                    # Compare both capture artifacts and every planning input
                    # against the exact files consumed by the saved report.
                    from orchestration import (
                        _canonical_json_sha256,
                        _read_planning_evidence_bundle,
                    )
                    candidate_info = report.get("candidate_report")
                    candidate_path = (
                        candidate_info.get("path")
                        if isinstance(candidate_info, dict) else None
                    )
                    current_evidence = _read_planning_evidence_bundle(
                        self.data_dir, candidate_path
                    )
                    saved_evidence_hashes = report.get(
                        "planning_evidence_file_sha256"
                    )
                    current_evidence_hashes = current_evidence["file_sha256"]
                    planning_evidence_matches = (
                        isinstance(saved_evidence_hashes, dict)
                        and all(
                            isinstance(saved_evidence_hashes.get(key), str)
                            and saved_evidence_hashes.get(key) == digest
                            for key, digest in current_evidence_hashes.items()
                        )
                        and all(
                            isinstance(value, str)
                            for value in current_evidence_hashes.values()
                        )
                    )
                    # Compare the saved report with the same board object that
                    # passed preflight; never reopen a mutable capture path.
                    board = capture["board_data"]
                    board_calibration_matches = (
                        isinstance(board, dict)
                        and isinstance(current_evidence.get("vision_calibration"), dict)
                        and board.get("calibration_sha256")
                        == _canonical_json_sha256(
                            current_evidence["vision_calibration"]
                        )
                    )
                    provenance = report.get("capture_provenance")
                    capture_fields = (
                        "source_sha256", "capture_session_id", "captured_at",
                        "snapshot_id", "board_snapshot_id",
                    )
                    report_artifacts = report.get("capture_bundle_file_sha256")
                    pinned_artifacts = {
                        "board_json": pinned.get("board_bytes_sha256"),
                        "shooter_json": pinned.get("shooter_bytes_sha256"),
                        "pixel_audit_json": pinned.get("pixel_audit_bytes_sha256"),
                    }
                    capture_report_matches = (
                        planning_evidence_matches
                        and board_calibration_matches
                        and isinstance(board, dict)
                        and isinstance(provenance, dict)
                        and all(
                            isinstance(board.get(key), str)
                            and provenance.get(key) == board.get(key)
                            for key in capture_fields
                        )
                        and isinstance(report_artifacts, dict)
                        and all(
                            isinstance(report_artifacts.get(key), str)
                            and report_artifacts.get(key) == digest
                            for key, digest in pinned_artifacts.items()
                            if isinstance(digest, str)
                        )
                        and all(isinstance(value, str) for value in pinned_artifacts.values())
                    )
            except Exception:
                capture_evidence_valid = False
        verified_plan = (
            capture_evidence_valid
            and capture_report_matches
            and evidence_gate_passed
            and report.get("decision")
            == "VERIFIED_PLAN_AVAILABLE_BUT_LIVE_ACTIONS_DISABLED"
            and isinstance(planner, dict)
            and bool(planner.get("recommended_group"))
        )
        return {
            "paused": self.paused,
            "mode": "PAUSED" if self.paused else "PLAN_ONLY",
            "tap_enabled": False,
            "gameplay_ready": False,
            "plan_available": verified_plan,
            "plan_is_simulation_candidate": verified_plan,
            "plan_is_gameplay_verified": False,
            "plan_verification_status": (
                "SIMULATION_CANDIDATE_ONLY_NOT_GAMEPLAY_VERIFIED"
                if verified_plan else "NO_VERIFIED_PLAN"
            ),
            "shooter_observation_quality": {
                "colour_independently_verified": False,
                "ammunition_independently_verified": False,
                "slot_mapping_independently_verified": False,
                "interpretation": (
                    "STATUS does not trust saved verification claims; "
                    "shooter observations remain simulation-only."
                ),
            },
            "decision": report.get("decision", "NO_REPORT"),
            "evidence_gate_passed": evidence_gate_passed,
            "capture_evidence_valid": capture_evidence_valid,
            "capture_report_matches_current_capture": capture_report_matches,
            "board_calibration_matches_current_config": board_calibration_matches,
            "planning_evidence_matches_current_files": (
                planning_evidence_matches
                if capture_evidence_valid else False
            ),
            "touch_injection": False,
            "gameplay_actions_performed": False,
        }

    def plan(self):
        if self.paused:
            return {
                "accepted": False,
                "reason": "Controller is paused.",
                "touch_events_sent": False,
                "live_execution_allowed": False,
            }

        try:
            from orchestration import run_orchestration

            observation = self.data_dir / "board_observation_latest.json"
            shooters = self.data_dir / "shooter_detection.json"
            if not observation.is_file() or not shooters.is_file():
                return {
                    "accepted": False,
                    "mode": "PLAN_ONLY",
                    "reason": (
                        "A fresh screenshot capture is required. Run the capture "
                        "pipeline to create both board_observation_latest.json "
                        "and shooter_detection.json."
                    ),
                    "touch_events_sent": False,
                    "live_execution_allowed": False,
                    "gameplay_actions_performed": False,
                }
            from capture_preflight import validate_capture_pair
            capture = validate_capture_pair(observation, shooters)
            if capture.get("valid") is not True:
                return {
                    "accepted": False,
                    "mode": "PLAN_ONLY",
                    "reason": capture.get("reason", "Capture preflight failed."),
                    "touch_events_sent": False,
                    "live_execution_allowed": False,
                    "gameplay_actions_performed": False,
                }
            report = run_orchestration(
                data_dir=str(self.data_dir),
                observation_path=str(observation) if observation.is_file() else None,
                shooter_path=str(shooters) if shooters.is_file() else None,
            )
            planner = report.get("planner", {})
            evidence = report.get("evidence", {})
            evidence_gate_passed = (
                isinstance(evidence, dict)
                and evidence.get("evidence_gate_passed") is True
            )
            group = planner.get("recommended_group")
            verified_plan = (
                evidence_gate_passed
                and report.get("decision")
                == "VERIFIED_PLAN_AVAILABLE_BUT_LIVE_ACTIONS_DISABLED"
                and bool(group)
            )
            self.last_plan = report

            return {
                "accepted": True,
                "mode": "PLAN_ONLY",
                "plan_available": verified_plan,
                "plan_is_simulation_candidate": verified_plan,
                "plan_is_gameplay_verified": False,
                "plan_verification_status": (
                    "SIMULATION_CANDIDATE_ONLY_NOT_GAMEPLAY_VERIFIED"
                    if verified_plan else "NO_VERIFIED_PLAN"
                ),
                "shooter_observation_quality": {
                    "colour_independently_verified": False,
                    "ammunition_independently_verified": False,
                    "slot_mapping_independently_verified": False,
                    "interpretation": (
                        "Shooter observations are simulation-only; "
                        "independent verification is not available."
                    ),
                },
                "recommended_group": group if verified_plan else None,
                "decision": report.get("decision"),
                "evidence_gate_passed": evidence_gate_passed,
                "touch_events_sent": False,
                "live_execution_allowed": False,
                "gameplay_actions_performed": False,
            }
        except Exception as exc:
            return {
                "accepted": False,
                "mode": "PLAN_ONLY",
                "error": f"{type(exc).__name__}: {exc}",
                "touch_events_sent": False,
                "live_execution_allowed": False,
                "gameplay_actions_performed": False,
            }

    def execute(self, command):
        command = str(command).strip().upper()

        if command == "STATUS":
            return self.status()

        if command == "PAUSE":
            self.paused = True
            return {"accepted": True, "paused": True}

        if command == "RESUME":
            self.paused = False
            return {"accepted": True, "paused": False}

        if command == "PLAN":
            return self.plan()

        if command == "TAP":
            return {
                "accepted": False,
                "reason": "Live touch execution is disabled.",
                "touch_events_sent": False,
                "live_execution_allowed": False,
            }

        return {
            "accepted": False,
            "reason": "Unknown command.",
            "touch_events_sent": False,
            "live_execution_allowed": False,
        }
