import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPORT = ROOT / "data" / "build11av_control_readiness.json"


class SlimeController:
    def __init__(self):
        self.paused = False
        self.tap_enabled = False
        self.last_plan = None

    def readiness(self):
        try:
            return json.loads(REPORT.read_text())
        except Exception:
            return {}

    def status(self):
        report = self.readiness()
        return {
            "paused": self.paused,
            "tap_enabled": self.tap_enabled,
            "gameplay_ready": report.get("gameplay_ready", False),
            "touch_injection": report.get("checks", {}).get(
                "touch_injection", False
            ),
        }

    def plan(self):
        if self.paused:
            return {
                "accepted": False,
                "reason": "Controller is paused.",
                "touch_events_sent": False,
            }

        try:
            from level_loader import load_level
            from planner import plan_next_move

            state, audit = load_level()
            result = plan_next_move(state)
            self.last_plan = result

            return {
                "accepted": True,
                "mode": "PLAN_ONLY",
                "level_loaded": True,
                "plan_result": result,
                "touch_events_sent": False,
                "live_execution_allowed": False,
            }
        except Exception as exc:
            return {
                "accepted": False,
                "mode": "PLAN_ONLY",
                "error": str(exc),
                "touch_events_sent": False,
                "live_execution_allowed": False,
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
            }

        return {
            "accepted": False,
            "reason": "Unknown command.",
        }
