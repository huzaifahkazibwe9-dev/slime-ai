#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

SCREENSHOT="screenshots/level39.jpg"
OBSERVATION="data/board_observation_latest.json"
SHOOTER_PANEL="screenshots/shooter_panel.jpg"
SHOOTER_DATA="data/shooter_detection.json"

echo "SLIME AI — LOW-POWER BUILD PIPELINE"
echo "==================================="
echo "Project: $ROOT"
echo "Live game actions: DISABLED"
echo

if [[ ! -f "$SCREENSHOT" ]]; then
    echo "ERROR: Required screenshot not found: $SCREENSHOT" >&2
    exit 2
fi

echo "[1/9] Ingesting the board screenshot"
python screenshot_ingestor.py "$SCREENSHOT"

if [[ -f "$SHOOTER_PANEL" ]]; then
    echo
    echo "[2/8] Refreshing shooter-panel detection"
    python shooter_detector.py
elif [[ -f "$SHOOTER_DATA" ]]; then
    echo
    echo "[2/8] Using existing shooter detection JSON"
else
    echo "ERROR: Neither $SHOOTER_PANEL nor $SHOOTER_DATA exists." >&2
    exit 2
fi

echo
echo "[3/8] Integrating screenshot and shooter data"
python level_loader.py --observation "$OBSERVATION"

echo
echo "[4/8] Building provisional colour-region analysis"
python observation_region_audit.py --input "$OBSERVATION"

if [[ -f "data/conveyor_calibration.json" && -f "data/conveyor_visual_observations.json" ]]; then
    echo
    echo "[5/8] Auditing reachability against the latest screenshot"
    python reachability_auditor.py --board "$OBSERVATION"

    echo
    echo "[6/9] Applying screenshot-derived confidence and planning gates"
    python reachability_confidence.py --board "$OBSERVATION"
    python planning_gate.py

    echo
    echo "[7/9] Mapping lanes onto colour regions"
    python region_lane_mapper.py --board "$OBSERVATION"
else
    echo
    echo "[5-7/9] Skipping conveyor analysis: local calibration/observation files are missing"
fi

echo
echo "[8/9] Running evidence-gated dry-run orchestration"
python orchestration.py --observation "$OBSERVATION"

echo
echo "[9/9] Running central diagnostics and tests"
python main.py --observation "$OBSERVATION"
python -m unittest discover -q

echo
echo "BUILD PIPELINE COMPLETE"
echo "No game taps were performed."
echo "Colour truth and gameplay remain unverified."
echo "Live game actions remain disabled."
