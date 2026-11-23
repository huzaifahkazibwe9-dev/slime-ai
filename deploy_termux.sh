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
if [[ ! -f "screenshots/shooter_panel.jpg" && ! -f "data/shooter_detection.json" ]]; then
    echo "ERROR: Need shooter_panel.jpg or data/shooter_detection.json." >&2
    exit 2
fi
if [[ -f "screenshots/shooter_panel.jpg" ]] && ! command -v tesseract >/dev/null 2>&1; then
    echo "ERROR: Tesseract is required when shooter_panel.jpg is present." >&2
    echo "Install it in Termux with: pkg install tesseract" >&2
    exit 2
fi

echo
echo "[3/4] Installing declared Python dependencies"
python -m pip install -r requirements.txt

echo
echo "[4/4] Running the validated build pipeline"
bash build_pipeline.sh

echo
echo "TERMUX DEPLOYMENT CHECK COMPLETE"
echo "This is still a diagnostic build, not live-gameplay authorization."
echo "Game taps remain disabled."
