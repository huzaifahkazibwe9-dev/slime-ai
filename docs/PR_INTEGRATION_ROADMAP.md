# Pull Request Integration Roadmap

## Purpose

This repository currently has many open draft pull requests. A passing CI run on an individual branch does not establish that every branch can be merged independently or that the full stack is release-ready. This document records a conservative integration order and identifies overlapping work before consolidation.

## Integration rules

1. Keep `main` as the only release baseline; do not merge a child branch before its required parent.
2. Re-run CI on the exact final head SHA after every rebase or conflict resolution.
3. Merge only after reviewing the combined diff, not merely the individual PR's green status.
4. Preserve fail-closed behavior: missing, stale, mismatched, or malformed evidence must never produce an actionable plan.
5. Keep live game input and purchases disabled. A plan is advisory/simulation-only.
6. Do not describe screenshot provenance checks as proof of authentic capture, correct calibration, human label truth, or gameplay accuracy.

## Recommended consolidation groups

### A. Core simulation and safety baseline

Review the integrated geometry, vision/OCR, bonded-group, and simulation changes first:
- #19 geometry integration
- #20 vision/OCR integration
- #21 bonded-group invariants
- #22 simulation and multi-batch safeguards
- #30 shooter-record preflight
- #31 simulator snapshot/restore

Branch comparison confirms #30 is 10 commits ahead of #22 with no commits behind, and #31 is 115 commits ahead of #30 with no commits behind. Thus #31 already contains the #22/#30 line of work; those three should be treated as one cumulative simulator candidate, not three independent merges. However, #31 is diverged from the geometry, vision, and bonded-invariant branches (#19–#21), and is 132 commits ahead of its main baseline while one commit behind current main. File-level comparison narrows the conflict surface: #19 changes geometry modules that #31 does not touch, so it can be integrated as a separate foundation. #20 overlaps #31 in `shooter_detector.py`, `shooter_loader.py`, and their tests; both contain strict OCR-token handling, atomic bonded-group withholding, and geometry-observation type checks, but the validation details differ. Resolve those files by preserving the stronger checks from both patches and run their combined regression suite. #21 changes `game_state.py` plus `test_execution_engine.py`; #31 changes `execution_engine.py` and the same execution-engine test file, so review the shared tests and ensure the bonded-state invariants remain exercised after integration. Rebase/integrate those foundations deliberately, then run combined CI on the exact candidate SHA. #31 deserves focused review of snapshot schema compatibility, event-history validation, and rollback semantics.

### B. Screenshot ingestion and capture provenance

Treat #38–#48 as one dependency chain rather than independent merge candidates:
- Template/cache validation: #38–#42
- Numeric bounds and shooter capture metadata: #43–#45
- Cross-stage hash/session consistency: #46
- Fresh paired capture requirements: #47–#48

Merge in dependency order only after a final combined CI run. Hashes and timestamps provide consistency checks, not cryptographic authenticity or proof that the visual calibration matches the game board.

### C. Human-labelled colour evaluation

#35 establishes the evaluation framework. #36 and #38–#39 extend template and cache validation. #49–#54 contain related source-image verification, coverage, and compatibility work.

Potential overlap requiring explicit resolution:
- #52 adds source-image verification implementation.
- #53 documents the verification matrix.
- #54 adds compatibility tests.
These are currently sibling branches based on #51. Consolidate their distinct changes into one sequential branch or rebase them one at a time; do not merge all three independently without checking duplicate hunks and tests.

No real-game colour accuracy claim is justified until a representative, independently human-reviewed screenshot dataset has been populated and evaluated.

### D. Independent pixel audit and planning gate

Treat #55–#60 as a second dependency chain:
- #55–#56 sampling geometry and provenance
- #57 independent source-pixel reproduction
- #58 capture-pipeline gate
- #59 planning preflight
- #60 capture-identity binding

These checks establish internal consistency of stored samples against source bytes. They do not prove calibration alignment, human label correctness, or gameplay performance.

### E. Status freshness and saved-plan identity

#61 and #62 extend the capture chain so status output cannot advertise a plan backed by stale or different evidence. Keep them after #60. Confirm legacy report handling is intentionally fail-closed and documented.

## Known overlap and cleanup candidates

- #9 and #10 both modify `multi_batch_planner.py` and `test_multi_batch_planner.py`; #11 contains the combined iterable/batch-shape and shot-input preflight changes. The distinct changes visible in the PR patches are represented in #11, so #9 and #10 are strong supersession candidates. Confirm commit ancestry and full diffs before closing them.
- #14 and #25 make the same four-line production change in `shooter_loader.py` to reject non-object geometry observations. Their tests differ: #25 additionally checks the `None` compatibility case. Retain one implementation and combine the stronger test coverage rather than merging both PRs independently.
- #15 and #29 have identical one-line workflow diffs removing the `pull_request.branches: [main]` restriction. #37, already merged into `main`, implements that same workflow change. Both #15 and #29 are superseded by #37 unless a fresh diff reveals additional changes.
- #52, #53 and #54 are sibling PRs. All three carry the same source-image verification implementation and shared test additions; #53 adds the test-matrix document, while #54 adds two compatibility tests. Consolidate the implementation once, then retain the unique documentation and compatibility tests in a single follow-up branch.
- #1–#8 and #10 may contain changes already incorporated into later integrated PRs. Audit commit ancestry and file-level diffs before closing or merging; PR titles alone are not sufficient evidence of duplication.

## Geometry foundation carried into the simulator branch
The remaining shooter-crop comparison guard from #20 was also carried over: mean and 99th-percentile pixel-difference tolerances must be finite numeric values in the inclusive 0–255 channel-difference range. Regression tests cover negative, over-range, non-finite, boolean, and string values. This complements the earlier panel aspect-ratio and sample-quality threshold checks.



The non-overlapping geometry foundation from #19 has been copied into #31: strict finite numeric validation for screen centres, image dimensions, board bounds and grid sizes; segment-side and span checks; and contextual error reporting for invalid calibration entries. Geometry adapter and coordinate-separation regression coverage was added to the existing simulator test module. This is a branch-level integration only; the exact combined candidate must pass CI before the geometry foundation is considered validated with the simulator.

## Bonded-state invariants carried into the simulator branch
Multi-batch checkpoint/rollback audit: resume verifies the schedule fingerprint, validates the completed report prefix, restores the simulator snapshot, and deterministically replays the completed prefix before accepting the checkpoint. It then compares the restored simulator report and final batch metrics with replay. Pre-tick batch transitions snapshot shooter ammo/position/lap/selection/return flags, storage occupancy, returned IDs, event length, and scheduler seen-groups; failed reactivation/selection/shot-input transitions roll back those mutations. Tick failures intentionally retain the attempted tick and partial event history, matching the simulator's failure accounting. No additional state-loss defect was identified in this review. These are internal consistency safeguards, not proof that the abstract conveyor timing matches the live game.

Snapshot/restore audit found that the simulator snapshot preserved group IDs and lifecycle history but did not enforce the PR #21 maximum bonded-component size of three. The simulator constructor now rejects groups larger than three, so snapshot restoration fails closed through the same constructor path; tests cover both direct construction and a tampered snapshot. The simulator snapshot intentionally stores abstract conveyor state, not screen-space geometry: verified coordinates remain in the separate GameState/geometry observation path and must not be inferred from a restored simulator snapshot.



PR #21's stronger bonded-state checks have now been reconciled into the cumulative simulator branch (#31). The state model validates bond-list shape and member IDs, rejects invalid group IDs, requires reciprocal bond edges for selection, rejects inconsistent group IDs, and audits connected components independently so oversized groups are reported rather than silently treated as singles. Regression tests cover malformed metadata, asymmetric links, conflicting/non-string group IDs, and components larger than three. This is still a candidate-branch integration; combined CI is required before considering the reconciliation validated.

## Shooter detector hardening carried into the simulator branch

The cumulative simulator branch (#31) initially lacked input validation already present in the vision-quality branch (#20): finite/range checks for panel aspect-ratio tolerance and colour-sample quality thresholds. Those guards have now been carried into #31's `shooter_detector.py`, with regression tests for NaN, infinity, out-of-range values, booleans, and non-numeric values. This is a targeted conflict-resolution step, not a full integration of #20; the remaining overlapping shooter-loader/detector changes still require review and combined tests.

## Release-candidate exit criteria

A release candidate is not ready until all of the following are true:

- The selected dependency chain is integrated into one candidate branch.
- CI passes on the exact candidate commit for every supported Python version.
- The complete test suite passes after integration, including regression tests across capture, cache, planning, and status.
- The Termux build script passes syntax validation; device installation and runtime checks remain a separate later stage.
- A representative human-labelled screenshot dataset has been independently reviewed and evaluated before making colour-accuracy claims.
- Real-device calibration alignment and game-state interpretation have been manually verified.
- No live taps, automated purchases, or other game actions are enabled without a separate, explicit safety and reliability review.

## Current status

This roadmap is an integration plan, not evidence that any unmerged PR has been incorporated. As of this document, only PR #37 is known to be merged into `main`; the other referenced PRs remain subject to fresh status checks.
