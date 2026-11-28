# Slime AI — Offline Milestone Status

Last updated: 2026-11-28 (reliability-offline-hardening-2026-11)

This file tracks progress toward a reliable, fully tested **offline** puzzle-solving system.
It is deliberately conservative. Nothing is marked complete without evidence.

## Legend
- **Complete** — Independently verified offline with tests or fixtures
- **Partial** — Substantial progress, remaining gaps documented
- **Blocked** — Requires human evidence, real Android device data, or external input
- **Not started**

---

## 1. Android device validation
**Status: Blocked**

- Screenshot ingestion and device compatibility code exists
- Reproducible validation procedures are partially documented in README
- **Blocked on**: Actual device evidence from the target Android phone (screenshots, timings, failure modes under real Termux conditions)
- Do not claim device validation without real device evidence

## 2. Shooter detection validation
**Status: Partial / Blocked**

- Detection pipeline, sample-quality checks, and low-confidence filtering exist
- Measurement reporting is present
- Human-review annotation package is not yet complete
- **Blocked on**: Human-reviewed ground-truth labels for shooter identities, colours, and ammunition values
- Never invent ground-truth labels

## 3. End-to-end integration (offline)
**Status: Partial**

- Screenshot ingestion → board perception → conveyor simulation → planning → solver evaluation path exists
- Evidence gates and provenance checks are in place
- Dry-run orchestration is implemented
- Remaining work: tighter fixture coverage, clearer failure modes when evidence is incomplete, more regression tests around the full offline pipeline
- Note: 17 unit tests are currently skipped because private Level 39 / conveyor evidence fixtures are not present in the public repository

## 4. Reliability
**Status: Partial**

- Large number of unit tests already exist
- Safety flags (game taps disabled) are consistently enforced
- Data-integrity and fail-closed behaviour is strong in many modules
- New: `docs/OFFLINE_VALIDATION.md` added for clearer offline test/diagnostic commands
- Latest verified public CI run #1239 (2026-11-27): **635 tests ran, 0 failures, 17 skipped** on Python 3.12 and 3.14 (skips are for private evidence not shipped in the public repo)
- Added regression tests for non-uniform edge changes, empty boards, and undersized boards in the evidence coordinator
- Added fail-closed regression tests: coordinate() leaves no observation/report artefacts when extraction fails or grid size mismatches baseline
- Added fail-closed regression tests for screenshot ingestor: zero-byte, garbage-byte, and truncated-PNG inputs raise UnidentifiedImageError and leave no observation artefacts
- Added fail-closed regression tests: coordinate() leaves no artefacts on missing baseline, invalid baseline JSON, or calibration bounds mismatch
- Added fail-closed regression test: coordinate() leaves no artefacts on invalid capture_session_id
- Added human-review annotation schema and fail-closed validator (`docs/SHOOTER_ANNOTATION_SCHEMA.md`, `annotation_validator.py`)
- Strengthened annotation validator: unique shooter IDs, range-checked and unique optional slot_index, and bonded_ids that reject self-references, unknown IDs, and internal duplicates
- Annotation validator now requires optional notes field to be a string when present
- Annotation validator now requires bonded components to be of size at most 3 (matching confirmed-groups rule of 2 or 3)
- Added regression tests for valid triple and rejected quadruple bonded groups
- Annotation validator rejects boolean and float ammunition values (matches GameState type(ammo) is not int rule)
- Added regression tests for boolean and float ammo rejection
- Added regression tests for zero ammunition (accepted), empty shooters list (accepted), whitespace-only colour (rejected), and non-list/missing shooters (rejected)
- Planning gate now validates report structure before evaluation: malformed report roots, results collections, positions, scenario collections, and scenarios are reported explicitly and fail closed.
- Added five planning-gate regression tests for malformed structure handling; any malformed structure blocks otherwise-valid sibling scenarios.
- Annotation validator now enforces the same strict capture_session_id rules used by the rest of the pipeline (alphanumeric start, limited charset, length 1..128).
- Added regression tests for invalid annotation version, naive/malformed timestamps, empty annotator, invalid session IDs, uppercase snapshot hex, and boolean slot_index.
- Added regression tests for session-ID length boundary (exactly 128 characters accepted, 129 rejected), empty bonded_ids lists accepted, non-string snapshot IDs rejected, and snapshot digests missing the sha256: prefix rejected.
- Added focused regression tests for Shooter.valid() (boolean/float/negative ammo, bad direction, rotation_progress range/non-finite/boolean, self-bonds, duplicate bonds, revealed requirements) and GameState.validate() (empty/non-rectangular board, capacity exceeded, ID mismatch, invalid shooter, unknown occupied, duplicate occupation).
- Fixed unreachable oversized bonded-group validation error: GameState.validate() now uses a size-unrestricted component walk so groups larger than 3 are reported (selection paths continue to use bonded_group() which returns empty for them).
- Added LifeState regression tests covering available() cap, update() life gain and maximum enforcement, and seconds_until_next() timing.
- Added GameState.validate() regression tests for inconsistent group_id values within a bonded component and for bonded groups exceeding size 3.
- Added regression tests for two independent bonded pairs and for a size-3 component plus an isolated shooter (confirming connected-component size limits do not reject valid multi-component annotations).
- Hardened Shooter.valid() to reject empty/whitespace/None shooter IDs and empty/whitespace color strings when the shooter is revealed (aligns with annotation-validator rules; unrevealed shooters may still omit color).
- Added three regression tests covering empty/whitespace/None IDs, revealed empty/whitespace color rejection, and unrevealed empty color tolerance.
- Added ResourceManager regression tests covering IDLE start, ANALYSE/LEARN mode transitions, PLAY permanently blocked while taps disabled, invalid mode rejection, pause/resume/stop semantics, and status safety flags.
- Public unit tests now 753 tests ran / 0 failures / 17 skipped (local verification after adding ResourceManager safety and mode-transition regression tests)
- Created `evidence/final/` directory with explicit documentation of still-required external evidence
- Evidence coordinator now takes a single immutable byte snapshot of a screenshot so extraction, SHA-256 digest and EXIF parsing are bound to the same content even if the source path is replaced during processing
- Evidence coordinator stages both JSON output files before publishing either; a staging-write failure leaves the prior evidence files unchanged and temporary files are cleaned up
- Added a regression test that injects a report-staging failure and checks preservation of both existing evidence files
- Remaining work:
  - Additional edge-case and regression tests
  - Clearer documentation of known limitations
  - Continuous documentation of blockers

---

## Current focus (this branch)

Priority order for offline-verifiable work:
1. Strengthen regression tests around evidence gates and provenance
2. Improve documentation of remaining offline gaps
3. Add or tighten fixtures for the end-to-end offline path
4. Keep STATUS.md accurate after every meaningful change

## Rules reminder
- Never enable gameplay taps or live automation
- Never fabricate device results or human labels
- Never claim 100% completion without evidence
- Work only on feature branches and open draft PRs

---

## Honest completion estimate (offline-completable portion only)

Approximate offline-completable progress: **~90%**

This number will only be revised upward when concrete, tested improvements land. It will never be inflated.
