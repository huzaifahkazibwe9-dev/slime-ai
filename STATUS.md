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
- Hardened Shooter.valid() to reject empty/whitespace/None shooter IDs and empty/whitespace color strings when the shooter is revealed (aligns with annotation-validator rules; unrevealed shooters may still omit color).
- Added three regression tests covering empty/whitespace/None IDs, revealed empty/whitespace color rejection, and unrevealed empty color tolerance.
- Added ResourceManager regression tests covering IDLE start, ANALYSE/LEARN mode transitions, PLAY permanently blocked while taps disabled, invalid mode rejection, pause/resume/stop semantics, status safety flags, task-duration recording on stop/pause, and rejection of unknown task names.
- Hardened LifeState.update() and seconds_until_next() to fail closed (no-op / return 0) on non-finite now or last_regeneration timestamps. Added regression tests for non-finite inputs and negative elapsed (elapsed clamped to 0).
- Public unit tests now 759 tests ran / 0 failures / 17 skipped (local verification after hardening LifeState against non-finite timestamps and adding corresponding regression tests)
- Created `evidence/final/` directory with explicit documentation of still-required external evidence
- Evidence coordinator now takes a single immutable byte snapshot of a screenshot so extraction, SHA-256 digest and EXIF parsing are bound to the same content even if the source path is replaced during processing
- Evidence coordinator stages both JSON output files before publishing either; a staging-write failure leaves the prior evidence files unchanged and temporary files are cleaned up
- Added a regression test that injects a report-staging failure and checks preservation of both existing evidence files
- Added a symmetric regression test that injects an observation-staging failure and checks preservation of both existing evidence files
- Public unit tests now 760 tests ran / 0 failures / 17 skipped (local verification after adding the observation-staging failure regression)
- Converted shooter_order_planner ad-hoc run_tests into proper unittest coverage for ordering, bonded-group adjacency, capacity, duplicate IDs, board immutability, and prepare_groups edge cases (empty/non-list, invalid capacity, empty/non-string group and shooter IDs).
- Added proper unittest coverage for identity_tracker.validate_observations (injected shooters/positions; missing frame_id, unknown IDs, per-frame duplicate position/shooter, strict verified=True including rejection of string/int truthy values)
- Added proper unittest coverage for firing_observation.validate_observation (all eight calibrated positions, wrong direction/lane, out-of-board cells, boolean/float ammo and cell coordinates, unconfirmed observation, ammo non-decrease)
- Public unit tests now 812 tests ran / 0 failures / 17 skipped (local verification after shooter_order_planner unit tests)
- Converted sequential_firing_simulator ad-hoc run_tests into proper unittest coverage for sequential exposure, empty cells, ammo limits, colour blocking, all four directions, empty sequences, invalid inputs (ammo, direction, board shape), lane bounds, case-insensitive colour matching, zero-ammo exhaustion, and source-board immutability.
- Public unit tests now 828 tests ran / 0 failures / 17 skipped (local verification after sequential_firing_simulator unit tests)
- Converted firing_simulator ad-hoc run_tests into proper unittest coverage. Hardened ammo and lane validation to reject boolean values (consistent with other modules). Added regressions for matching removal, colour blocking, all four directions, board immutability, lane-cleared boundary, zero ammo, empty colour, negative/boolean ammo, out-of-range lane, unknown direction, invalid board shape, and simulated-board None cells.
- Converted color_components ad-hoc run_tests into proper unittest coverage for 4-directional connectivity, diagonal separation, orthogonal merging, edge detection, size sorting, sample-cell limits, empty boards, None/empty-string colours, and rectangular boards. Hardened find_components to return {} on empty input.
- Public unit tests now 854 tests ran / 0 failures / 17 skipped (local verification after color_components unit tests)
- Converted firing_adapter ad-hoc run_tests into proper unittest coverage for all four simulator directions, colour blocking, empty lanes, unverified colour, case-insensitive matching, invalid direction/lane (non-int, boolean, out-of-range), boundary lanes, direction-map completeness, and board immutability.
- Public unit tests now 870 tests ran / 0 failures / 17 skipped (local verification after firing_adapter unit tests)
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

Approximate offline-completable progress: **~94%**

This number will only be revised upward when concrete, tested improvements land. It will never be inflated.
