# Slime AI

Slime Loop analysis and planning project for Termux.

## Current workflow

1. Ingest a complete screenshot:
   `python screenshot_ingestor.py screenshots/level39.jpg`
2. Validate the saved legacy vision dataset (this checks the existing baseline, not the newly ingested observation):
   `python validate_vision.py`
3. Integrate the latest screenshot observation with the detected shooter panel:
   `python screenshot_observation_loader.py`
4. Run the unit suite:
   `python -m unittest discover -v`

The screenshot observation loader checks board dimensions, per-cell RGB data,
colour counts, and snapshot identity before constructing a candidate
`GameState`. Shooter panel coordinates remain separate from conveyor
coordinates. All shooter accessibility, colour verification, gameplay
verification, and live tapping remain disabled.

**Important:** a successful extraction or integration is not proof that
the classifier matches the game's true tile colours or that a move is safe.
Do not enable live actions based only on these reports.
