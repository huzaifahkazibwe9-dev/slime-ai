# Capture and simulator integration

This branch combines the simulator snapshot work with the screenshot evidence pipeline.

## Evidence flow

1. `capture_pipeline.py` reads one screenshot byte snapshot, stages it in a private temporary directory, verifies the staged bytes, and pins its SHA-256.
2. Board and shooter extraction both consume the same staged file and must identify that same source hash, capture session, and timestamp. The staged file is removed after the run, including on extraction failure.
3. `source_pixel_audit.py` independently reproduces saved RGB samples from the original screenshot bytes.
4. `capture_preflight.py` requires a recent, matching board/shooter pair and matching source-pixel audit.
5. `orchestration.py` reads the three JSON artifacts once, validates those parsed objects, and passes the same board/shooter objects to the level loader.
6. The report binds the candidate plan to the exact capture identity. `STATUS` validates one pinned capture bundle and only shows a saved plan when its provenance matches.

## Simulator boundary

The conveyor and multi-batch simulator remains an abstract model. Snapshot/restore and checkpoint replay validate internal simulator-state consistency; they do not establish that simulated timing, storage behaviour, or shooter motion matches the live game.

## Integration safeguards

- Shooter panel extraction and verification use the same immutable screenshot bytes.
- Existing simulator-side OCR parsing, shooter ammo validation, geometry checks, and bonded-group safeguards are retained.
- Low-confidence bonded observations are withheld as a complete group rather than converted into independent shooters.
- Planning and execution remain simulation-only. Android touch injection and automatic power-up purchases remain disabled.

## Validation status

This document describes intended architecture, not a claim of live-game correctness. CI on this combined branch is required before considering the integration validated. Device deployment and gameplay verification are separate future gates.
