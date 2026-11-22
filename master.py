from pathlib import Path
import ast
import json
import sqlite3
import time

ROOT = Path(__file__).resolve().parent
REPORT = ROOT / "master_report.txt"

REQUIRED = [
    "game_state.py",
    "planner.py",
    "solver.py",
    "vision.py",
    "board_loader.py",
    "level_loader.py",
    "shooter_detector.py",
    "shooter_loader.py",
    "learner.py",
    "command_dispatcher.py",
    "macro_bridge.py",
    "main.py",
    "controller.py",
    "resource_manager.py",
]

lines = []

def log(message=""):
    print(message)
    lines.append(str(message))

log("SLIME AI MASTER CHECK")
log("=" * 45)
log("Project: " + str(ROOT))
log("Game tapping: DISABLED")
log("Time: " + time.strftime("%Y-%m-%d %H:%M:%S"))
log()

log("1. PROJECT FILES")
for name in REQUIRED:
    path = ROOT / name
    log(f"[{'FOUND' if path.is_file() else 'MISSING'}] {name}")

log()
log("2. PYTHON SYNTAX CHECK")

syntax_errors = []
for path in sorted(ROOT.glob("*.py")):
    try:
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        log("[PASS] " + path.name)
    except Exception as exc:
        syntax_errors.append(path.name)
        log(f"[FAIL] {path.name}: {exc}")

log()
log("3. JSON DATA CHECK")

json_files = sorted((ROOT / "data").glob("*.json"))
for path in json_files:
    try:
        json.loads(path.read_text(encoding="utf-8"))
        log("[PASS] " + path.name)
    except Exception as exc:
        log(f"[FAIL] {path.name}: {exc}")

if not json_files:
    log("No JSON files found.")

log()
log("4. DATABASE CHECK")

db = ROOT / "data" / "learning.db"
if db.is_file():
    try:
        connection = sqlite3.connect(
            f"file:{db}?mode=ro", uri=True
        )
        integrity = connection.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0]
        log("Database integrity: " + integrity)

        tables = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()

        log("Tables: " + str([t[0] for t in tables]))

        if any(t[0] == "observations" for t in tables):
            counts = connection.execute(
                "SELECT source, COUNT(*) FROM observations "
                "GROUP BY source"
            ).fetchall()
            log("Learning records: " + str(counts))

        connection.close()
    except Exception as exc:
        log("[FAIL] " + str(exc))
else:
    log("Learning database not found.")

log()
log("5. SCREENSHOT AND DATA CHECK")

for relative in [
    "screenshots/level39.jpg",
    "data/vision_level39.json",
    "data/shooter_detection.json",
    "data/color_matches.json",
]:
    path = ROOT / relative
    log(f"[{'FOUND' if path.is_file() else 'MISSING'}] {relative}")

log()
log("6. SAFETY")
log("No game taps performed.")
log("No source files modified.")
log("No existing files deleted.")

log()
log("7. SUMMARY")
log("Python files checked: " + str(len(list(ROOT.glob("*.py")))))
log("Syntax errors: " + str(len(syntax_errors)))
log("Required files missing: " + str(
    sum(not (ROOT / name).is_file() for name in REQUIRED)
))

REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
print("\nReport saved to:", REPORT)
print("MASTER CHECK COMPLETE")
