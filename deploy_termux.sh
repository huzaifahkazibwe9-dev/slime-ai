#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

echo "SLIME AI — FINAL TERMUX DEPLOYMENT"
echo "=================================="
echo "This prepares and validates the local project."
echo "It does not tap the game or enable MacroDroid."

if [[ ! -d ".git" ]]; then
    echo "ERROR: Run this script from a cloned Slime AI repository." >&2
    exit 2
fi

if [[ -z "${PREFIX:-}" || "${PREFIX}" != *"/com.termux/"* ]]; then
    echo "ERROR: This deployment script is intended for Termux." >&2
    exit 2
fi

echo
echo "[1/4] Synchronising the project"
git pull --ff-only

echo
echo "[2/4] Checking local screenshot inputs"
if [[ ! -f "screenshots/level39.jpg" ]]; then
    echo "ERROR: screenshots/level39.jpg is missing." >&2
    exit 2
fi
if [[ ! -f "data/shooter_capture_config.json" \
      && ! -f "screenshots/shooter_panel.jpg" \
      && ! -f "data/shooter_detection.json" ]]; then
    echo "ERROR: Need data/shooter_capture_config.json, shooter_panel.jpg, or data/shooter_detection.json." >&2
    exit 2
fi
if [[ -f "screenshots/shooter_panel.jpg" || -f "data/shooter_capture_config.json" ]] && ! command -v tesseract >/dev/null 2>&1; then
    echo "ERROR: Tesseract is required for shooter-panel detection." >&2
    echo "Install it in Termux with: pkg install tesseract" >&2
    exit 2
fi

echo
echo "[3/5] Checking the Termux Python environment"
if ! command -v python >/dev/null 2>&1; then
    echo "ERROR: Python is not available in this Termux environment." >&2
    echo "Install it with: pkg install python" >&2
    exit 2
fi
python -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else "ERROR: Slime AI requires Python 3.10 or newer.")'
if ! python -m pip --version >/dev/null 2>&1; then
    echo "ERROR: Python pip is unavailable in this Termux environment." >&2
    echo "Repair the Termux Python installation before deployment." >&2
    exit 2
fi
python --version

echo
echo "[4/5] Installing declared Python dependencies"
python -m pip install -r requirements.txt

echo
echo "[5/5] Running the validated build pipeline"
bash build_pipeline.sh

echo
echo "TERMUX DEPLOYMENT CHECK COMPLETE"
echo "This is still a diagnostic build, not live-gameplay authorization."
echo "Game taps remain disabled."
