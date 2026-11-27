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

Latest verified public-repository outcome (GitHub Actions run #1239, 2026-11-27):
- 635 tests ran on Python 3.12 and 3.14
- 0 failures / 0 errors
- 17 skipped (private Level 39 vision, conveyor consistency, conveyor timeline, and reachability evidence fixtures are not present in the public repository)
- The 17 skipped tests are not counted as passing, and their private fixtures are not represented as public evidence.

Local verification after adding annotation session-id alignment and field-edge regression tests (invalid version, naive timestamp, empty annotator, invalid session IDs, uppercase snapshot, boolean slot): 653 tests ran, 0 failures, 17 skipped.

Local verification after adding GameState/Shooter validation regression tests: **676 tests ran, 0 failures, 17 skipped**.

Local verification after fixing oversized bonded-group reporting in GameState.validate() and adding LifeState timing/capacity regression tests: **681 tests ran, 0 failures, 17 skipped**.

Local verification after adding empty-shooters colour mapping regression test: **682 tests ran, 0 failures, 17 skipped**.

The evidence coordinator stages the observation and report JSON files before replacing either published file. A regression test verifies that a failure while staging the report leaves both prior outputs unchanged and cleans the temporary files.

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
