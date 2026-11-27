# Final evidence pack

This directory separates **automated CI evidence** from the external evidence still required to establish full project completion.

## Present and verified

- [`ci_runs.json`](ci_runs.json) records selected successful pull-request CI runs, tested Python versions, test counts and checks. The latest feature entry is run #1214 with 1,253 passing unit tests per Python version. The JSON also records corrected intermediate CI failures in `superseded_failures` for traceability. It currently contains 28 successful CI snapshots and six corrected failures.

These are GitHub-hosted CI results for feature-branch commits. PRs #143–#166 add the completion evidence registry, structural GameState validation, direct shot input validation, an eleven-case four-direction ray reference corpus, strict fixture-schema tests, candidate-search truncation boundary checks and a five-case dry-run outcome corpus, including a modeled board-clearing candidate, a valid-but-unsolved candidate, a no-legal-group case, an unverified-provenance block and malformed-board rejection, and exact positive-integer validation of the dry-run candidate budget before the provenance gate. The bonded-group reference corpus adds three synthetic cases for sequential two-member simulation, shared-target depletion and three-member atomic selection, all checked against exact expected outcomes. A six-case negative corpus covers asymmetric and malformed bonds, unknown links, inconsistent group IDs and over-limit components, with fail-closed validation and source-immutability assertions. An eight-case selectability corpus covers conveyor capacity boundaries, pre-existing conveyor/storage occupancy, duplicated occupancy IDs, repeated bond references and self-links; the direct selection helper now refuses these malformed states. Bonded storage transfers now move complete linked groups atomically; direct state, conveyor simulator and multi-batch tests cover exact/insufficient capacity, partial-group refusal and safe reactivation preflight. Checkpoint tests verify JSON resume equivalence through bonded return/reactivation cycles and reject forged partial return state. PR #165 adds a failure-injection test for rollback after successful bonded reactivation, asserting that a subsequent shot-recording failure restores the pre-transition occupancy, shooter state, event history and tick count. A second bonded regression distinguishes this pre-tick transaction from partial tick failure: if a later group hits full storage, earlier same-tick returns and events remain recorded. Scheduler output is checked for matching failure metadata and the absence of a resumable checkpoint after that failed partial tick. Canonical shooter-ID ordering also makes bounded candidate enumeration deterministic across dictionary insertion orders. The new cases distinguish no selectable move, a simulated-but-unsolved candidate, unverified capture provenance and malformed-state rejection. They are not Android/Termux device runs and do not validate visual ground truth or live-game behaviour.

## Required external evidence (not yet recorded here)

| Path | Required contents | Acceptance note |
|---|---|---|
| `device/termux_build_report.md` | Android version, device model family, Termux version, Python/dependency versions, clean install steps, exit codes, runtime results and limitations | Must be produced by an actual target-device run. Do not infer it from CI shell syntax. |
| `device/capture_manifest.json` | Capture session IDs, timezone-aware timestamps, screenshot dimensions, calibration/config hashes and source SHA-256 values | Every row must refer to an original screenshot that is retained for review. |
| `device/screenshots/` | Original screenshots or an access-controlled archive plus a verified manifest | Do not fabricate or silently retouch screenshots; avoid committing unnecessary personal information. |
| `human_review/board_reviewer_a.json`, `human_review/board_reviewer_b.json` | Independently completed board-label datasets | Human fields must not be copied from detector output. |
| `human_review/shooter_reviewer_a.json`, `human_review/shooter_reviewer_b.json` | Independently completed shooter visibility/position/colour/ammunition datasets | Ambiguous and unreadable samples must remain explicit. |
| `human_review/intake_audit.json`, `human_review/agreement_report.json` | Source-bound completeness and reviewer agreement outputs | Agreement is not itself proof of label truth; report coverage and limitations. |
| `reports/vision_validation_report.json` | Board classifier metrics, per-class support/errors and uncertainty | Must use independent labels from genuine captures. |
| `reports/shooter_validation_report.json` | Visibility, slot, colour and ammunition metrics with coverage | Keep each task separate; include missing OCR and ambiguous counts. |
| `reports/conveyor_validation_report.json` | Observed-versus-modeled conveyor transitions and timing | Each accepted mechanic must cite original captures and reviewer notes. |
| `reports/solver_validation_report.json` | Hand-checked reference states and expected solver outcomes | Distinguish supported mechanics, ambiguous rules and unproven optimality. |
| `reports/dependency_audit.md` | Dependency inventory, versions, audit date and findings | Must reflect the declared deployment environment. |
| `reports/known_limitations.md` | Unsupported mechanics, unresolved bugs and external blockers | No unsupported accuracy or win-rate claims. |
| `reports/final_completion_report.md` | All subsystem statuses, evidence links/hashes, test results and accepted exclusions | Publish 100% only when every required acceptance gate is closed. |

The expected paths are a checklist, not pre-filled evidence. Empty placeholders are intentionally avoided so no example data can be mistaken for actual test results.

## Preservation and integrity

Keep the original input artifacts, generated reports and their exact byte hashes together. Store human review labels separately from detector predictions. A SHA-256 digest establishes file identity, not authorship or correctness. Never store tokens, passwords or other secrets in this directory.
