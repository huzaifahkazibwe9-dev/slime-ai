# Independent source-pixel audit

The source-pixel audit independently checks whether every saved board RGB sample
can be reproduced from the original screenshot bytes.

Run it with:

```bash
python source_pixel_audit.py data/board_observation_latest.json --source-image screenshots/level39.jpg
```

The audit verifies the screenshot SHA-256 and dimensions, declared grid and
calibration bounds, sample-centre coordinates, sampling-method identifier,
and every stored 3x3 median RGB value. Pixel medians are recomputed with Pillow
pixel reads and Python's `statistics.median`, separately from the NumPy-based
extraction implementation. It also checks whether saved board labels and colour
counts agree with the source-derived RGB samples and the current shared
classifier.

When an observation includes the ingestion `extraction_sha256`, the audit
recomputes that canonical payload fingerprint across image/grid dimensions,
bounds, sample centres, board labels, RGB samples, colour counts, and sampling
method. Missing or malformed fingerprints are reported as non-matching rather
than treated as verified. This digest detects accidental edits only when the
digest is not also recomputed; it is not an authenticity signature.

A mismatch is reported per board coordinate where applicable. Malformed or
incomplete source provenance and geometry are rejected rather than silently
accepted.

## What this does not prove

- Calibration bounds align with the visible game tiles.
- The screenshot depicts the intended or current game state.
- The shared colour classifier matches the game's true colour semantics.
- Human labels are correct or representative.
- Gameplay, solver recommendations, or live interactions are verified.

The report deliberately keeps `calibration_alignment_verified`,
`label_truth_independently_verified`, and `gameplay_verified` false, and
`game_taps_enabled` false. A successful pixel audit proves byte-level
reproducibility of the recorded samples only.


## Capture-pipeline integration

The capture pipeline now runs this audit automatically after board ingestion and
shooter detection, using the same screenshot byte snapshot whose SHA-256 was
pinned before the subprocesses ran. The pipeline fails closed unless every
stored RGB sample reproduces, the extraction payload fingerprint matches,
board labels agree with the shared classifier applied to source-derived RGB,
and colour counts match. A successful report is written to
`data/source_pixel_audit_latest.json`.

This integration strengthens source/payload consistency checks; it still does
not establish calibration alignment with visible game tiles or true game
colour semantics. It does not enable live game actions.


## Planning preflight requirement

The capture preflight now requires the latest pixel-audit report beside the board
observation. Its source hash, image dimensions, and grid dimensions must match
the current board capture; all samples must reproduce; the extraction
fingerprint and colour counts must match; and there must be zero classifier
label mismatches. A missing, stale, or incomplete report blocks planning and
requires rerunning the capture pipeline.

This is a consistency gate, not proof that the calibration bounds correspond to
the visible puzzle tiles or that the classifier reflects game semantics.
