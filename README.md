# Slime AI

Slime Loop analysis and planning project for Termux.

## One-command Termux deployment

When the project is ready to be installed on the phone, run from the cloned repository:

`bash deploy_termux.sh`

The deployment script synchronises the latest GitHub version, checks that it is running in Termux with Python 3.10+ and working `pip`, validates required local screenshot inputs, installs the declared Python dependencies, and runs the build pipeline. It refuses non-Termux environments and never taps the game.

To run only the local diagnostics without synchronising or installing dependencies, use:

`bash build_pipeline.sh`

The build script:
- creates a coordinate-grid shooter-panel calibration preview when no local capture configuration exists;
- ingests the saved Level 39 screenshot;
- uses the local same-capture configuration to extract and detect the shooter panel, or preserves existing evidence in diagnostic-only mode;
- integrates the screenshot and shooter data into a candidate game state;
- builds provisional colour regions;
- runs lane reachability, confidence and planning gates when local conveyor evidence files exist;
- performs dry-run orchestration, central diagnostics and unit tests.

It does not tap the game, start background loops, or change MacroDroid settings.

## Shooter-panel crop calibration

Do not guess panel coordinates or copy the illustrative bounds from the example
configuration. Create a coordinate-grid preview from the exact full screenshot:

`python calibrate_shooter_panel.py screenshots/level39.jpg`

Open `screenshots/shooter_calibration_grid.png` and identify the rectangle
containing the shooter panel. The grid labels are coordinates in the original
screenshot pixels, even when the preview is resized. Record the rectangle as
`[LEFT, TOP, RIGHT, BOTTOM]` in `data/shooter_capture_config.json`. The crop
must contain the complete calibrated shooter panel and preserve its expected
aspect ratio; the extraction and source-region comparison will reject invalid
bounds or a crop that does not match the screenshot. The preview is a manual
measurement aid only: it does not detect the panel, certify the coordinates,
or verify shooter identities. Keep gameplay actions disabled until the
resulting capture and game observations are independently checked.

## Manual workflow

For a same-capture board/shooter run, create the local, ignored file
`data/shooter_capture_config.json` with the actual shooter-panel bounds in
full-screenshot coordinates, a session label, and the screenshot capture time:

```json
{
  "panel_bounds": [100, 100, 990, 680],
  "capture_session_id": "level39-session-01",
  "captured_at": "2026-11-23T12:30:00+03:00"
}
```

The numeric bounds above are illustrative only; replace them with the actual crop coordinates. The timestamp
must be the real capture time and include its UTC offset. The session label
must identify that capture; do not reuse it for a different screenshot.
When this file exists, the build pipeline ingests the board and generates the
shooter panel from the same source screenshot. Without it, legacy detection is
kept diagnostic-only and the evidence gate blocks planning.

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
   `python shooter_detector.py --source-screenshot screenshots/level39.jpg --panel-bounds LEFT TOP RIGHT BOTTOM --extract-panel --capture-session-id session-A --captured-at 2026-11-23T12:30:00+03:00`
   Replace the four bounds with the actual full-screenshot crop coordinates.
   `--extract-panel` creates the calibrated panel image from that screenshot,
   then verifies its source region. The loader and readiness coordinator block
   planning if the provenance does not match.
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
