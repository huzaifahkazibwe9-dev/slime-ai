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

if [[ ! -f "data/shooter_capture_config.json" ]]; then
    echo "[Calibration] Creating a coordinate-grid preview for manual shooter-panel bounds"
    python calibrate_shooter_panel.py "$SCREENSHOT" \
        --output screenshots/shooter_calibration_grid.png
    echo "No crop bounds were inferred; planning remains blocked until capture evidence is calibrated."
fi


if [[ -f "data/shooter_capture_config.json" ]]; then
    echo "[1/11] Ingesting board and shooter panel from one calibrated capture"
    python capture_pipeline.py "$SCREENSHOT"
elif [[ -f "$SHOOTER_DATA" ]]; then
    echo "[1/11] Ingesting board screenshot without overwriting existing shooter evidence"
    python screenshot_ingestor.py "$SCREENSHOT"
    echo "[2/11] Preserving existing shooter detection; capture provenance will be rechecked"
elif [[ -f "$SHOOTER_PANEL" ]]; then
    echo "[1/11] Ingesting board screenshot"
    python screenshot_ingestor.py "$SCREENSHOT"
    echo "[2/11] Running legacy shooter detection (provenance remains unverified)"
    python shooter_detector.py
else
    echo "ERROR: Need data/shooter_capture_config.json, $SHOOTER_PANEL, or $SHOOTER_DATA." >&2
    exit 2
fi

echo
echo "[3/11] Integrating screenshot and shooter data"
python level_loader.py --observation "$OBSERVATION"

echo
echo "[4/11] Building provisional colour-region analysis"
python observation_region_audit.py --input "$OBSERVATION"

if [[ -f "data/conveyor_calibration.json" && -f "data/conveyor_visual_observations.json" ]]; then
    echo
    echo "[5/13] Synchronising conveyor observations to this screenshot"
    python snapshot_sync.py --board "$OBSERVATION"

    echo
    echo "[6/13] Building user-confirmed identity and candidate reports"
    python identity_auditor.py --board "$OBSERVATION"
    python conveyor_identity_matcher.py

    echo
    echo "[7/13] Auditing reachability against the latest screenshot"
    python reachability_auditor.py --board "$OBSERVATION"

    echo
    echo "[8/13] Applying screenshot-derived confidence and planning gates"
    python reachability_confidence.py --board "$OBSERVATION"
    python planning_gate.py

    echo
    echo "[9/13] Mapping lanes onto colour regions"
    python region_lane_mapper.py --board "$OBSERVATION"
else
    echo
    echo "[7-9/13] Skipping conveyor analysis: local calibration/observation files are missing"
fi

echo
echo "[10/13] Running evidence-gated dry-run orchestration"
python orchestration.py --observation "$OBSERVATION"

echo
echo "[11/13] Running central diagnostics"
python main.py --observation "$OBSERVATION"

echo
echo "[12/13] Assessing readiness from the same screenshot evidence"
python readiness_coordinator.py --observation "$OBSERVATION" --shooters "$SHOOTER_DATA"

echo
echo "[13/13] Running the complete unit-test suite"
python -m unittest discover -q

echo
echo "BUILD PIPELINE COMPLETE"
echo "No game taps were performed."
echo "Colour truth and gameplay remain unverified."
echo "Live game actions remain disabled."
