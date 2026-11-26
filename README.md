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

## Exact-match board-analysis reuse

Screenshot ingestion fingerprints both the complete screenshot bytes (SHA-256)
and the canonical calibration JSON. If the latest observation contains a
structurally valid board extraction with both fingerprints and image dimensions
matching exactly, the board pixel classification is reused instead of repeated.
Any screenshot change, calibration change, missing/corrupt cache, or shape/count
mismatch forces a full extraction. This is exact duplicate-input reuse only;
there is no perceptual-similarity shortcut and no cached gameplay decision or
action is reused. Capture provenance is refreshed for each ingestion, and all
gameplay/tap safety flags remain disabled. The optimisation saves board
classification work on repeated identical inputs, but actual battery savings
must be measured on the target Android device.

## Dynamic-board simulation profiling

The dynamic-board simulator reports local `time.perf_counter` measurements for region-graph rebuild count and elapsed time, shot simulation time, and shooter-lane inspection time. Region graphs are still rebuilt after every successful pixel removal to preserve correctness as connected components change. These measurements are diagnostic simulation timings only; they are not Android gameplay latency or a device-speed guarantee. Any incremental graph-update optimisation must first demonstrate equivalence against full rebuilds across representative board transitions.

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

## Shooter sample-quality checks

Each of the 12 fixed-grid panel observations now compares its centre colour
patch with the surrounding local context. The diagnostic records local RGB
contrast and median absolute deviation, and labels the sample as distinct or
low-confidence. This helps flag points that may have landed on panel
background or a noisy boundary instead of a shooter circle. It is a quality
heuristic, not circle detection, colour identity verification, or proof that a
slot is available. All 12 observations remain non-selectable; only the
existing first-row OCR path is used, and lower-row ammunition is not inferred.
The fixed grid and its offsets still require validation against the complete
panel in a real capture.

## Low-confidence shooter filtering

New shooter-panel observations include a local sample-quality status. When a
sample is labelled `LOW_CONFIDENCE_SAMPLE`, the screenshot loader excludes
that shooter from the candidate game state rather than treating a background
or noisy patch as a reliable colour. If that shooter belongs to a confirmed
bonded group, the entire group is withheld rather than loading an incomplete
group. Legacy shooter files without the optional quality field remain
compatible. This is a conservative input filter, not proof of shooter
identity, accessibility, or correct colour mapping; gameplay and tap gates
remain disabled.

## Human-reviewed shooter observation evaluation

The repository now includes a blank-label template builder, an offline
evaluator for shooter-panel visibility assumptions, calibrated slot positions,
colour classification and ammunition OCR, structured OCR failure statuses
with a fail-closed runtime loader, plus a multi-capture aggregator. Each labelled capture is bound to its exact
detector JSON and original screenshot, and human labels remain separate from
detector outputs. See
[docs/SHOOTER_OBSERVATION_EVALUATION.md](docs/SHOOTER_OBSERVATION_EVALUATION.md)
for the review protocol, OCR status meanings, batch manifest and metric
limitations. Synthetic unit tests cover the workflow; no real-game accuracy
result is claimed until genuine captures are manually reviewed.

## Multi-capture combined visual review
The batch report preserves source-artifact SHA-256 hashes for the board, shooter, pixel audit and screenshot alongside completed review-file hashes.


The combined review pipeline can now re-verify and aggregate multiple completed board-and-shooter review bundles. It rejects duplicate screenshot hashes, duplicate capture sessions, duplicate bundle IDs, and paths that escape the batch-manifest directory. Board-colour and shooter metrics remain separate, with pooled sample support shown for each task. See [docs/COMBINED_VISUAL_REVIEW_BATCH.md](docs/COMBINED_VISUAL_REVIEW_BATCH.md). This workflow is for offline evaluation only; it does not enable live taps or purchases.

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

The one-command build pipeline runs these stages automatically and preserves
the same screenshot/shooter capture bundle throughout. When diagnosing a
single stage manually, use this order:

1. Ingest the current game screenshot:
   `python screenshot_ingestor.py screenshots/level39.jpg`
2. Capture the shooter panel from that same screenshot using the calibrated
   full-image crop and the same capture session/timestamp. Legacy detector
   invocation without source-screenshot provenance remains diagnostic-only.
3. Integrate the explicit observation and matching shooter data:
   `python level_loader.py --observation data/board_observation_latest.json --shooters data/shooter_detection.json`
4. Build provisional board colour regions:
   `python observation_region_audit.py --input data/board_observation_latest.json`
5. Synchronise conveyor observations to the current board capture:
   `python snapshot_sync.py --board data/board_observation_latest.json`
6. Prepare the unverified identity template, then build the human-confirmed
   identity audit and candidate report:
   `python prepare_identity_observations.py --board data/board_observation_latest.json`
   Complete `data/shooter_identity_observations.json` with independently
   user-confirmed records, then run:
   `python identity_auditor.py --board data/board_observation_latest.json`
   `python conveyor_identity_matcher.py`
   The template generator never overwrites an existing observation file and
   never sets confirmation flags. Without valid user-confirmed records,
   identity and candidate reports remain blocked; the program does not infer
   or fabricate labels.
7. Trace reachability against the latest screenshot:
   `python reachability_auditor.py --board data/board_observation_latest.json`
8. Apply screenshot-derived confidence and planning gates:
   `python reachability_confidence.py --board data/board_observation_latest.json`
   `python planning_gate.py`
9. Map calibrated lanes to provisional colour regions:
   `python region_lane_mapper.py --board data/board_observation_latest.json`
10. Run evidence-gated dry-run orchestration:
    `python orchestration.py --observation data/board_observation_latest.json --shooters data/shooter_detection.json`
11. Run central diagnostics:
    `python main.py --observation data/board_observation_latest.json --shooters data/shooter_detection.json`
12. Assess readiness from the same evidence bundle:
    `python readiness_coordinator.py --observation data/board_observation_latest.json --shooters data/shooter_detection.json`
13. Run the complete unit-test suite:
    `python -m unittest discover -v`

No stage taps the game or changes gold, inventory, or power-up state. A
candidate recommendation remains a simulation-only result.

## User-confirmed bonded shooter groups

The build pipeline also prepares `data/bonded_groups_confirmed.json` before
shooter detection, but only when the file is absent. The initial file has
`verified_by_user: false` and an empty group list. It does not infer or add
pairs. To enable bonded-group candidates, manually confirm the exact currently
detected shooter IDs and edit the file according to
[`docs/USER_CONFIRMED_BONDS.md`](docs/USER_CONFIRMED_BONDS.md).
The detector, matcher, planner and `STATUS` compare the config's exact SHA-256;
changing the file invalidates prior candidate reports and saved plans.

## Human-confirmed shooter identity

The build pipeline now validates physical shooter-to-conveyor-position identity
from an explicit, local user-confirmed observation file. It does not infer
physical identity from fixed panel positions or colour similarity.

Create `data/shooter_identity_observations.json` only after checking the
current capture. The required JSON schema, field meanings, current-frame
coverage rules, source matching and limitations are documented in
[`docs/USER_CONFIRMED_IDENTITY.md`](docs/USER_CONFIRMED_IDENTITY.md).
The file lives under the ignored `data/` directory and is not committed.

During the normal build pipeline, `identity_auditor.py` writes
`data/identity_audit_report.json`, then
`conveyor_identity_matcher.py` writes
`data/conveyor_identity_candidates.json`. Both bind their reports to the
exact board, calibration, visual observation, identity observation and shooter
detection inputs. Missing, stale or unconfirmed records keep candidate
matching blocked.

A passing identity audit confirms only the user-checked physical
shooter-to-position mapping for one capture. It does not verify panel colour
classification, ammunition OCR, firing behaviour, colour equivalence with
board tiles, or gameplay. Live game taps and purchases remain disabled.

## Supported Python versions

The automated test matrix covers Python 3.10, 3.11, 3.12 and 3.14. Each CI job checks shell-script syntax, compiles the Python modules, and runs the full unit suite. This is host-CI coverage; actual Termux installation and Android-device behaviour still require separate validation.

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

## Saved source-pixel audit status contract

Review-template preparation and combined review evaluation validate the saved
source-pixel audit's status fields as well as its screenshot hash and reproduced
measurements. The audit must explicitly confirm that its source-image hash and
dimensions were checked, while label truth, calibration alignment, gameplay,
and game taps remain explicitly unverified. Missing, null, or contradictory
status fields invalidate the review evidence, even if the artifact digest is
updated to match the altered file.

## Strict JSON inputs for capture, planning and review evidence

Strict UTF-8 JSON parsing is also enforced by the runtime board and confidence loaders, shooter and panel-slot loaders, screenshot-observation loader, conveyor identity snapshot reader, snapshot synchroniser, and legacy level loader. This prevents the planner from bypassing the duplicate-key and non-standard-number protections applied to capture/review artifacts. This is a parsing-integrity control only; it does not authenticate evidence or establish visual/gameplay correctness.

The same parser contract is applied at the wider evidence and planning boundaries: capture preflight, planning-gate snapshots, reachability audits and confidence reports, conveyor consistency/geometry/timeline and identity reports, firing observations/simulations, visual transition auditors, calibration and identity trackers, and the remaining board/shooter diagnostic readers. Duplicate names are rejected at every object depth, and `NaN`/infinities are not accepted as JSON numbers. Readers that fingerprint evidence continue hashing the exact original bytes separately from parsing.

The orchestration layer now uses the same strict parser for saved reports, pinned planning artifacts, and the board/shooter/pixel-audit capture bundle. If any of those inputs contain duplicate keys or invalid numeric values, evidence loading fails closed rather than presenting the artifact as current. The readiness coordinator returns its conservative fallback for malformed evidence, and the independent pixel-audit entry point reports invalid source observations as a controlled validation error.

The capture and review workflows use strict UTF-8 JSON parsing for calibration,
board and shooter observations, pixel audits, human-review datasets, review
manifests, and batch manifests. Duplicate object keys (including nested keys)
and non-standard numeric constants such as `NaN` and `Infinity`, exponents that overflow the finite floating-point range, and nonzero values that underflow to zero are rejected,
so each accepted evidence file has one unambiguous parsed representation.
This is a parsing-integrity check, not an authenticity signature; exact source
hashes and independent screenshot checks remain separate requirements.

## Capture evidence status contract

The capture pipeline now requires the board observation to explicitly keep
`same_board_state_confirmed`, `gameplay_verified`,
`vision_classification_verified`, and `game_taps_enabled` set to
`false`. It also requires shooter observation-quality flags for colour,
ammunition, and slot mapping to remain explicitly unverified. Missing, null,
or true values fail the capture-output validation gate.

These flags describe the limits of the current evidence; they are not a
verification of visual accuracy or gameplay. Human review and device-side
validation are still required, and live game taps and purchases remain
disabled.

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


## Human visual review workflow

Prepare board-colour and shooter-observation templates from one screenshot with `python prepare_visual_review.py path/to/original-screenshot.png --config data/shooter_capture_config.json`. After manually completing both templates, evaluate them together with `evaluate_visual_review_bundle.py`. The two stages and their provenance checks are documented in [docs/COMBINED_VISUAL_REVIEW.md](docs/COMBINED_VISUAL_REVIEW.md). The metrics remain separate and user-labelled; this workflow does not claim gameplay verification.

### Immutable screenshot observations

The screenshot transition pipeline reads each input screenshot once and uses
the same immutable byte snapshot for board extraction and SHA-256 provenance.
It does not reopen a mutable path between visual analysis and hashing. This
prevents an observation from combining pixels from one file version with the
digest of a later replacement. The reported digest identifies the bytes read;
it does not independently verify the screenshot's capture time or gameplay
state.


### Screenshot file metadata consistency

Screenshot ingestion now reads bytes through one open file descriptor and
checks the descriptor's device, inode, size, modification time and change time
before and after the read. A file modified in place during the read is rejected.
The reported `file_modified_at` comes from that same descriptor, rather than a
later path lookup that could describe a replacement file. This remains a
filesystem modification timestamp, not proof of when the screenshot was
captured.


### Observation board/grid shape validation

Before comparing two screenshot observations, the transition pipeline checks
that each extracted board is a rectangular list whose row and column counts
match that observation's declared calibration grid. Invalid, boolean,
non-positive, oversized, truncated or over-wide grid declarations are
rejected rather than compared as if they were complete boards. A rejected
shape never verifies a transition or enables game taps.


### Observation payload schema validation

The transition evaluator rejects non-object observations, invalid screenshot
dimensions, non-finite or out-of-frame sampling bounds, and board cells that do
not use the screenshot ingestor's known colour-label vocabulary. Matching
metadata alone is not sufficient: each payload must independently satisfy
the same basic shape and sampling constraints before two boards can be
compared. Invalid payloads remain unverified and cannot enable game taps.

### Observation sample-window geometry validation

The observation gate also reproduces the screenshot ingestor's rounded sample
centres from the declared grid and bounds. It rejects calibrations whose
adjacent 3x3 sample windows would overlap, or whose rounded centres would put
a sample window outside the screenshot. This prevents metadata that is merely
inside the image rectangle from being accepted when the ingestor could not
have sampled the declared grid safely.


### Capture orchestrator source snapshot stability

Before either board or shooter processing starts, the capture orchestrator
reads the original screenshot through one open file descriptor. It compares
device, inode, size, modification time and change time before and after the
read, and verifies the byte count against the descriptor size. An in-place
write or pathname replacement during the read is rejected when descriptor
metadata changes. The pipeline therefore fails closed rather than accepting
a capture whose source changed during acquisition. This is a file-consistency
guarantee, not proof of screenshot authenticity or capture time.


### Capture preflight status revalidation

Before a screenshot/shooter pair enters the readiness path, capture preflight
rechecks that the board's transition/gameplay flags and the shooter's
independent colour, ammunition and slot-mapping flags remain explicitly false.
It also validates the source-pixel audit's required positive checks and
unverified status flags. Missing or contradictory fields fail closed. This
protects the later readiness boundary if evidence files are edited after the
capture pipeline has written them.


### Pixel-audit sample coverage consistency

Capture preflight checks the source-pixel report's detailed coverage against
the calibrated grid. The schema version must be supported, the sample and
reproduced-sample counts must both equal the grid cell count, the pixel
mismatch count must be exactly zero, and both pixel- and label-mismatch lists
must be empty. Boolean values are not accepted as integer counts. These
consistency checks complement the existing screenshot hash, dimensions,
capture-session and status checks.


### Pixel-audit binding to the complete board observation

The source-pixel audit now records a canonical SHA-256 digest of the complete
parsed board-observation object, in addition to the screenshot-byte digest.
Capture preflight recomputes that digest from the board object it actually
received and requires an exact match. Any later edit to board labels, RGB
samples, calibration metadata or other payload fields invalidates the earlier
pixel audit and blocks readiness. This binds report consistency; it is not a
digital signature and does not establish that the board labels match game
truth.


### Concurrent capture-run serialization

The screenshot-to-board/shooter capture pipeline takes an exclusive operating
system file lock before reading configuration or writing its shared latest
capture reports. Concurrent invocations serialize rather than interleaving
their board, shooter and pixel-audit outputs. The lock is released on normal
completion or error, and the operating system releases it if the process exits.
This protects the shared-file workflow from competing capture runs; it does not
replace the per-capture screenshot hash, session, timestamp or payload checks.


### Standalone screenshot-loader geometry validation

The direct screenshot-to-GameState loader now applies the same rounded sample
centre and non-overlapping 3x3 sampling-window checks as screenshot ingestion
and transition evaluation. The checks run even when an observation omits its
optional `sample_centres` metadata. The independent source-sample verifier
also rejects overlapping or out-of-image windows before indexing source pixels,
so callers cannot bypass the geometry gate by skipping orchestration preflight.


### Standalone loader's unverified-state requirement

The direct screenshot-to-GameState loader requires
`same_board_state_confirmed` to be explicitly false, alongside its existing
gameplay, colour-classification and game-tap restrictions. Missing or true
values are rejected; the loader cannot silently accept an observation that
claims the board state has already been confirmed.


### Standalone loader count and digest type checks

Saved colour counts must be exact positive integers; booleans and floating-point
values are rejected even when Python's numeric equality would make them compare
equal to integer totals. Screenshot SHA-256 values must use canonical lowercase
hexadecimal notation, matching the digests produced by the capture and audit
pipelines.


## Completion status and evidence

See the [final completion checklist](docs/FINAL_COMPLETION_CHECKLIST.md) and
[final completion audit](docs/FINAL_COMPLETION_AUDIT.md) for measurable
subsystem statuses, acceptance criteria and remaining external blockers.
Verified CI runs and the required device/human-review artifact layout are
indexed in [the final evidence pack](evidence/final/README.md). Passing CI is
not Android-device validation or proof of visual/gameplay correctness.


## Solver input-state validation

The simulator validates the structure of its input `GameState` before
searching. Malformed boards, rows, cells, shooter records and occupancy
containers are rejected with explicit validation errors rather than incidental
type exceptions. The direct shot API also checks ammunition, direction,
coordinates and board structure. Seven hand-checkable shot cases are stored in
`data/solver_reference_cases.json` and replayed by a table-driven test. See
[docs/SOLVER_VALIDATION_REFERENCE.md](docs/SOLVER_VALIDATION_REFERENCE.md)
for the reference test coverage and its limits.
