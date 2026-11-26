# Offline Validation Guide

This document describes the supported offline validation path for Slime AI.
It does **not** claim device validation or gameplay verification.

## Requirements

- Python 3.10+
- Dependencies from `requirements.txt` (`Pillow`, `numpy`)
- No live game interaction is performed by any command below

## Quick offline checks

```bash
# Syntax check of deployment scripts
bash -n build_pipeline.sh deploy_termux.sh

# Compile all Python modules
python -m compileall -q .

# Run the full unit test suite
python -m unittest discover -v
```

## Diagnostic / dry-run path (when fixtures exist)

```bash
# Central diagnostics (legacy or observation mode)
python main.py

# With a screenshot observation (if available)
python main.py --observation data/board_observation_latest.json
```

## Safety reminders

- `GAME_TAPS_ENABLED` remains `False` in all supported entry points
- Planning and orchestration are dry-run only
- No command in this repository should tap the game or spend gold

## What this does **not** cover

- Real Android / Termux device behaviour
- Human-reviewed shooter identity labels
- Live conveyor timing under real game conditions

Those items remain blocked until evidence is supplied.
