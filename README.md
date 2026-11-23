# Slime AI

Slime Loop analysis and planning project for Termux.

## One-command Termux deployment

When the project is ready to be installed on the phone, run from the cloned repository:

`bash deploy_termux.sh`

The deployment script synchronises the latest GitHub version, checks required local screenshot inputs, installs the declared Python dependencies, and runs the build pipeline. It refuses non-Termux environments and never taps the game.

To run only the local diagnostics without synchronising or installing dependencies, use:

`bash build_pipeline.sh`

The build script:
- ingests the saved Level 39 screenshot;
- refreshes shooter detection if the shooter-panel crop exists;
- integrates the screenshot and shooter data into a candidate game state;
- builds provisional colour regions;
- runs lane reachability, confidence and planning gates when local conveyor evidence files exist;
- performs dry-run orchestration, central diagnostics and unit tests.

It does not tap the game, start background loops, or change MacroDroid settings.

## Manual workflow

1. Ingest a complete game screenshot:
   `python screenshot_ingestor.py screenshots/level39.jpg`
2. If the panel crop is available, refresh shooter detection:
   `python shooter_detector.py`
   This legacy invocation deliberately leaves shooter capture provenance
   unverified. To bind the panel crop to the same full screenshot used in
   step 1, supply the full screenshot, the exact crop bounds in that image,
   and the same explicit session ID and offset-aware capture timestamp to
   both ingestion and shooter detection. Example:
   `python screenshot_ingestor.py screenshots/level39.jpg --capture-session-id session-A --captured-at 2026-11-23T12:30:00+03:00`
   `python shooter_detector.py --source-screenshot screenshots/level39.jpg --panel-bounds LEFT TOP RIGHT BOTTOM --capture-session-id session-A --captured-at 2026-11-23T12:30:00+03:00`
   Replace the four bounds with the actual full-screenshot crop coordinates.
   The panel image must match that source region; the loader and readiness
   coordinator block planning if the provenance does not match.
3. Integrate the observation with shooter data:
   `python level_loader.py --observation data/board_observation_latest.json`
4. Build provisional colour regions:
   `python observation_region_audit.py`
5. If local conveyor calibration and visual-observation files exist, trace lanes:
   `python reachability_auditor.py --board data/board_observation_latest.json`
6. Apply confidence labels and the planning gate:
   `python reachability_confidence.py --board data/board_observation_latest.json`
   `python planning_gate.py`
7. Map lanes to regions:
   `python region_lane_mapper.py --board data/board_observation_latest.json`
8. Run evidence-gated dry-run orchestration:
   `python orchestration.py --observation data/board_observation_latest.json`
9. Run central diagnostics:
   `python main.py --observation data/board_observation_latest.json`
10. Run all unit tests:
    `python -m unittest discover -v`

## Validation scope

The screenshot-mode level loader validates:
- board and RGB grid dimensions;
- each saved colour label against the screenshot ingestor's RGB classifier;
- colour counts and screenshot snapshot identity;
- shooter IDs, bonds, and game-state consistency.

Shooter panel coordinates remain separate from conveyor coordinates. Detected shooters
remain inaccessible until independently verified. Screenshot-derived board confidence
is provisional (boundary cells require confirmation); it never marks cells confirmed.
The planner now requires the loaded board snapshot ID to match the independently
synchronized evidence reports, preventing stale plans from being applied to a new board.

## Legacy baseline audit

`python validate_vision.py` validates the older
`data/vision_level39.json` baseline. It does **not** validate the newly ingested
`data/board_observation_latest.json` file. Use the screenshot-mode commands above
for the new observation.

## Safety and evidence limits

Successful extraction, structural validation, or simulation is not proof that
the classifier matches the game's true tile colours or that a move is safe.
Shooter identities, shooter-to-board colour mappings, conveyor timing, and tile
removal semantics still require live-game evidence. All gameplay verification
flags remain false and live game tapping remains disabled.
