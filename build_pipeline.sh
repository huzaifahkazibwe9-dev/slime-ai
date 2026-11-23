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

if [[ ! -f "data/shooter_capture_config.json" ]]; then
    echo "[Calibration] Creating a coordinate-grid preview for manual shooter-panel bounds"
    python calibrate_shooter_panel.py "$SCREENSHOT" \
        --output screenshots/shooter_calibration_grid.png
    echo "No crop bounds were inferred; planning remains blocked until capture evidence is calibrated."
fi

if [[ ! -f "$SCREENSHOT" ]]; then
    echo "ERROR: Required screenshot not found: $SCREENSHOT" >&2
    exit 2
fi

if [[ -f "data/shooter_capture_config.json" ]]; then
    echo "[1/9] Ingesting board and shooter panel from one calibrated capture"
    python capture_pipeline.py "$SCREENSHOT"
elif [[ -f "$SHOOTER_DATA" ]]; then
    echo "[1/9] Ingesting board screenshot without overwriting existing shooter evidence"
    python screenshot_ingestor.py "$SCREENSHOT"
    echo "[2/9] Preserving existing shooter detection; capture provenance will be rechecked"
elif [[ -f "$SHOOTER_PANEL" ]]; then
    echo "[1/9] Ingesting board screenshot"
    python screenshot_ingestor.py "$SCREENSHOT"
    echo "[2/9] Running legacy shooter detection (provenance remains unverified)"
    python shooter_detector.py
else
    echo "ERROR: Need data/shooter_capture_config.json, $SHOOTER_PANEL, or $SHOOTER_DATA." >&2
    exit 2
fi

echo
echo "[3/9] Integrating screenshot and shooter data"
python level_loader.py --observation "$OBSERVATION"

echo
echo "[4/9] Building provisional colour-region analysis"
python observation_region_audit.py --input "$OBSERVATION"

if [[ -f "data/conveyor_calibration.json" && -f "data/conveyor_visual_observations.json" ]]; then
    echo
    echo "[5/9] Auditing reachability against the latest screenshot"
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
echo "[9/11] Running central diagnostics"
python main.py --observation "$OBSERVATION"

echo
echo "[10/11] Assessing readiness from the same screenshot evidence"
python readiness_coordinator.py --observation "$OBSERVATION" --shooters "$SHOOTER_DATA"

echo
echo "[11/11] Running the complete unit-test suite"
python -m unittest discover -q

echo
echo "BUILD PIPELINE COMPLETE"
echo "No game taps were performed."
echo "Colour truth and gameplay remain unverified."
echo "Live game actions remain disabled."
