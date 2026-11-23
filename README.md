# Slime AI

Slime Loop analysis and planning project for Termux.

## Screenshot-to-state workflow

1. Ingest a complete game screenshot:
   `python screenshot_ingestor.py screenshots/level39.jpg`
2. Validate the ingested observation while building a candidate game state:
   `python level_loader.py --observation data/board_observation_latest.json`
3. Run the central read-only diagnostic using the same observation:
   `python main.py --observation data/board_observation_latest.json`
4. Run all unit tests:
   `python -m unittest discover -v`

The screenshot-mode level loader validates:
- board and RGB grid dimensions;
- each cell's saved colour label against the screenshot ingestor's RGB classifier;
- colour counts and screenshot snapshot identity;
- shooter IDs, bonds, and state consistency.

Shooter panel coordinates remain separate from conveyor coordinates. Detected shooters
remain inaccessible until independently verified. The adapter does not infer empty
cells, real-game colour truth, shooter-to-board colour mappings, conveyor identities,
or tile removals from a single screenshot.

## Legacy baseline audit

`python validate_vision.py` validates the older
`data/vision_level39.json` baseline. It does **not** validate the newly ingested
`data/board_observation_latest.json` file. Use the screenshot-mode level loader
above for the new observation.

## Safety and evidence limits

Successful extraction, structural validation, or simulation is not proof that
the classifier matches the game's true tile colours or that a move is safe.
All gameplay verification flags remain false and live game tapping remains
disabled. Do not enable live actions based only on these reports.
