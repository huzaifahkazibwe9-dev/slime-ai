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
        verified_plan = (
            evidence_gate_passed
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
            "decision": report.get("decision", "NO_REPORT"),
            "evidence_gate_passed": evidence_gate_passed,
            "touch_injection": False,
            "gameplay_actions_performed": False,
        }

    def _capture_preflight(self, observation_path, shooter_path):
        """Require a recent, explicitly ingested board/shooter capture pair."""
        try:
            board = json.loads(observation_path.read_text(encoding="utf-8"))
            shooters = json.loads(shooter_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return False, f"Capture evidence is missing or invalid: {exc}"

        if not isinstance(board, dict) or not isinstance(shooters, dict):
            return False, "Capture evidence must contain JSON objects."

        provenance = shooters.get("capture_provenance")
        if not isinstance(provenance, dict):
            return False, "Shooter capture provenance is missing."

        if provenance.get("verified") is not True:
            return False, "Shooter capture provenance is not verified."
        if (
            not isinstance(board.get("source_sha256"), str)
            or board.get("source_sha256") != provenance.get("source_sha256")
        ):
            return False, "Board and shooter evidence do not share a screenshot hash."
        if (
            not board.get("capture_session_id")
            or board.get("capture_session_id") != provenance.get("capture_session_id")
        ):
            return False, "Board and shooter evidence do not share a capture session."
        if (
            not board.get("captured_at")
            or board.get("captured_at") != provenance.get("captured_at")
        ):
            return False, "Board and shooter evidence do not share a capture timestamp."

        try:
            from snapshot_sync import validate_capture_freshness
            freshness = validate_capture_freshness(
                board.get("captured_at"),
                provenance.get("captured_at"),
                max_age_seconds=300,
                max_skew_seconds=120,
            )
        except (TypeError, ValueError) as exc:
            return False, f"Capture freshness could not be verified: {exc}"

        if freshness.get("fresh") is not True:
            return False, "Screenshot capture is stale or timestamps are misaligned; run the capture pipeline again."

        return True, None

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
