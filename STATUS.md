# Slime AI — Offline Milestone Status

Last updated: 2026-11-27 (reliability-offline-hardening-2026-11 + annotation edge tests)

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
- Latest public unit-test run (this environment, 2026-11-27): **618 tests ran, 0 failures, 17 skipped** (skips are for private evidence not shipped in the public repo)
- Added additional edge-case regression tests for the human-review annotation validator (boolean/float ammo rejection, empty shooters, naive timestamps, session-id spaces, empty id/color, extra-field tolerance)
- Added regression tests for non-uniform edge changes, empty boards, and undersized boards in the evidence coordinator
- Added fail-closed regression tests: coordinate() leaves no observation/report artefacts when extraction fails or grid size mismatches baseline
- Added fail-closed regression tests for screenshot ingestor: zero-byte, garbage-byte, and truncated-PNG inputs raise UnidentifiedImageError and leave no observation artefacts
- Added fail-closed regression tests: coordinate() leaves no artefacts on missing baseline, invalid baseline JSON, or calibration bounds mismatch
- Added fail-closed regression test: coordinate() leaves no artefacts on invalid capture_session_id
- Added human-review annotation schema and fail-closed validator (`docs/SHOOTER_ANNOTATION_SCHEMA.md`, `annotation_validator.py`)
- Created `evidence/final/` directory with explicit documentation of still-required external evidence
- Evidence coordinator now takes a single immutable byte snapshot of a screenshot so extraction, SHA-256 digest and EXIF parsing are bound to the same content even if the source path is replaced during processing
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

Approximate offline-completable progress: **~69%**

This number will only be revised upward when concrete, tested improvements land. It will never be inflated.
