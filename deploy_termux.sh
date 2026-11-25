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
echo "[1/5] Synchronising the project"
git pull --ff-only

echo
echo "[2/5] Checking local screenshot inputs"
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
NEED_TESSERACT=0
if [[ -f "data/shooter_capture_config.json" ]] \
   || { [[ ! -f "data/shooter_detection.json" ]] \
        && [[ -f "screenshots/shooter_panel.jpg" ]]; }; then
    NEED_TESSERACT=1
fi

echo
echo "[3/6] Checking the Termux Python environment"
if ! command -v pkg >/dev/null 2>&1; then
    echo "ERROR: Termux package manager (pkg) is unavailable." >&2
    exit 2
fi
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
echo "[4/6] Installing Termux-native Python dependencies"
# NumPy and Pillow contain native extensions; use Termux's packaged builds.
pkg install -y python-numpy python-pillow
if [[ "$NEED_TESSERACT" -eq 1 ]]; then
    pkg install -y tesseract
fi

echo
echo "[5/6] Verifying installed libraries and OCR data"
python -c 'import numpy; from PIL import Image; print("NumPy:", numpy.__version__); print("Pillow:", Image.__version__ if hasattr(Image, "__version__") else "available")'
if [[ "$NEED_TESSERACT" -eq 1 ]]; then
    if ! command -v tesseract >/dev/null 2>&1; then
        echo "ERROR: Tesseract installation did not provide the tesseract command." >&2
        exit 2
    fi
    if ! tesseract --list-langs 2>/dev/null | grep -Fxq "eng"; then
        echo "ERROR: Tesseract English language data (eng) is unavailable." >&2
        exit 2
    fi
fi
# Dependencies are already supplied by Termux packages. Do not let pip
# replace native Android builds with incompatible PyPI wheels.
python -m pip install --no-deps -r requirements.txt

echo
echo "[6/6] Running the validated build pipeline"
bash build_pipeline.sh

echo
echo "TERMUX DEPLOYMENT CHECK COMPLETE"
echo "This is still a diagnostic build, not live-gameplay authorization."
echo "Game taps remain disabled."
