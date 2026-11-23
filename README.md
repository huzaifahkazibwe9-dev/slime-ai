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

## Performance profiling and OCR workload
Board screenshot ingestion also uses NumPy to compute each cell's 3×3
per-channel median from an in-memory pixel array, instead of issuing nine PIL
pixel reads per cell. Its extraction time and sampling method are included in
the board observation report. This preserves the existing median-sampling
rule while reducing Python-level per-pixel overhead; actual speedup depends on
the phone, image dimensions, and NumPy build.


The shooter detector records local processing measurements in
`data/shooter_detection.json` under `performance`: total shooter-detection
time, accumulated ammunition OCR time, OCR call count, and observed panel-slot
count. These timings use a monotonic high-resolution clock and are diagnostic
measurements, not end-to-end gameplay latency or a device speed guarantee.

All 12 panel slots are still sampled for colour/layout observations. OCR is
currently restricted to the four first-row slots because lower rows are not yet
verified as readable; launching OCR for those slots added work without producing
trusted ammunition values. This is a workload reduction, not permission to
select lower-row shooters. They remain non-selectable until independently
verified. Further speed tuning must be benchmarked on the actual phone and must
not weaken screenshot freshness, provenance, or action-safety gates.

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

## Bonded-shooter confirmation

The detector does not infer bonded relationships from fixed screen positions.
By default it records no bonded groups. If the current game screen independently
shows a bonded group and you have confirmed its membership, create the local,
git-ignored file `data/bonded_groups_confirmed.json`:

```json
{
  "verified_by_user": true,
  "bonded_groups": [
    ["top_1", "top_2"]
  ]
}
```

Replace the example IDs and membership with what is actually visible in the
current game. The file is optional; without it, all detected shooters are
treated as unbonded for diagnostic purposes. Groups must contain two or three
known shooter IDs, without duplicate or overlapping membership. This explicit
confirmation is separate from visual detection and does not enable gameplay
actions.

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

## Planning evidence versus gameplay verification

The planning gate reports `planning_evidence_verified` only when at least one candidate passes every provenance, freshness, identity, ammunition, conveyor-timing, and confidence check. This permits an evidence-backed **dry-run recommendation** without claiming that the game has been played or that a move was executed. `gameplay_verified` remains false, `game_taps_enabled` remains false, and `actions_performed` remains false. Orchestration and the planner require this separation and reject reports that claim gameplay verification or enable taps.

## Safety and evidence limits

Successful extraction, structural validation, or simulation is not proof that
the classifier matches the game's true tile colours or that a move is safe.
Shooter identities, shooter-to-board colour mappings, conveyor timing, and tile
removal semantics still require live-game evidence. All gameplay verification
flags remain false and live game tapping remains disabled.

## Shop power-ups and gold

The four bottom shop buttons are represented in `powerups.py`, in left-to-right
order:

1. **Extra Tray** — increases conveyor capacity.
2. **Magic Glove** — selects a board circle, including an unseen one, for the conveyor.
3. **Angel Slime** — removes pixels matching the colour of the selected circle.
4. **Dragon Roar** — removes all board pixels of the selected colour.

Gold, prices, stock/charges, and the number of Extra Tray slots added are
tracked only when observed. Unknown values remain unknown; the model does not
guess shop prices or purchase automatically. Power-up effects are currently
candidate planning descriptions only: no game button is pressed and no board
state is changed. The planner produces separate use-readiness and purchase-eligibility decisions. It also adds transparent heuristic scores for observed board impact, conveyor urgency, purchase cost relative to observed gold, and preserving a last known charge. These scores are explicitly not calibrated win probabilities and do not establish a globally optimal move. Ordinary-move and power-up scores remain separate until gameplay outcomes establish a validated common value model. Automatic purchase and use remain disabled: no game button is pressed and no gold is spent.


### Reusing evolving-board search

The orchestration pipeline shares one evolving-board search result with the capacity-aware scheduler instead of repeating the same bounded search. The scheduler validates that a supplied result preserves its source state, matches the current remaining-pixel count, and contains a structurally valid group sequence before reuse. This removes redundant search work while retaining separate scheduling and simulation diagnostics. It does not improve the search heuristic itself or establish real-device gameplay speed; live gameplay remains unverified and taps remain disabled.
