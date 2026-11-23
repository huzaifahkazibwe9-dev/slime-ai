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
        return {
            "paused": self.paused,
            "mode": "PAUSED" if self.paused else "PLAN_ONLY",
            "tap_enabled": False,
            "gameplay_ready": False,
            "plan_available": bool(planner.get("recommended_group")),
            "decision": report.get("decision", "NO_REPORT"),
            "evidence_gate_passed": (
                evidence.get("evidence_gate_passed") is True
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
            report = run_orchestration(
                data_dir=str(self.data_dir),
                observation_path=str(observation) if observation.is_file() else None,
                shooter_path=str(shooters) if shooters.is_file() else None,
            )
            planner = report.get("planner", {})
            group = planner.get("recommended_group")
            self.last_plan = report

            return {
                "accepted": True,
                "mode": "PLAN_ONLY",
                "plan_available": bool(group),
                "recommended_group": group,
                "decision": report.get("decision"),
                "evidence_gate_passed": report.get(
                    "evidence", {}
                ).get("evidence_gate_passed") is True,
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
