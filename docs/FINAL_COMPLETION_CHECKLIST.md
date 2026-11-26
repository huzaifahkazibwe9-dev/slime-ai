# Final completion checklist

**Audit date:** 2026-11-26  
**Repository:** [`huzaifahkazibwe9-dev/slime-ai`](https://github.com/huzaifahkazibwe9-dev/slime-ai)  
**Status vocabulary:** `CI VERIFIED` means the listed automated checks passed on the referenced PR branch. `PARTIAL` means code/tests exist but real-world evidence or coverage is incomplete. `BLOCKED` means external device or human evidence is required. `NOT VERIFIED` means no reproducible evidence was located in the audited repository tree.

## Current engineering status

| ID | Area | Status | Evidence / files | Remaining acceptance criteria |
|---|---|---|---|---|
| CAP-01 | Screenshot byte provenance | CI VERIFIED | `screenshot_ingestor.py`, `capture_pipeline.py`, PRs #135/#138 | Keep the source screenshot, capture config, session and timestamp together for every device run; preserve original bytes and hashes. |
| CAP-02 | Board observation schema, dimensions and grid shape | CI VERIFIED | `observation_pipeline.py`, PRs #132/#133 | Continue rejecting malformed and incompatible payloads; all newly accepted schema versions need matching regression tests. |
| CAP-03 | Rounded 3×3 sample geometry | CI VERIFIED | `screenshot_ingestor.py`, `screenshot_observation_loader.py`, PRs #134/#140 | Verify calibration alignment against genuine target-device screenshots; geometric consistency alone does not prove that bounds are drawn around the game board. |
| CAP-04 | Pixel-audit completeness and board-payload binding | CI VERIFIED | `source_pixel_audit.py`, `capture_preflight.py`, PRs #137/#138 | Retain independently reproducible source screenshots and audit reports; do not treat byte consistency as label truth. |
| CAP-05 | Concurrent capture serialization | CI VERIFIED | `capture_pipeline.py`, PR #139 | Confirm lock behavior on the target Termux filesystem and ensure all supported capture entry points use the shared pipeline. |
| CAP-06 | Standalone loader status/type checks | CI VERIFIED | `screenshot_observation_loader.py`, PRs #140–#142 | Keep direct-loader contract aligned with the capture/preflight schema as it evolves. |
| HUM-01 | Paired visual review workflow | PARTIAL | `prepare_visual_review.py`, `evaluate_visual_review_bundle.py`, `prepare_shooter_review_pair.py`, `shooter_review_intake_audit.py`; [review guide](COMBINED_VISUAL_REVIEW.md), [intake guide](REVIEW_INTAKE_READINESS.md) | Complete paired review datasets using independent human reviewers, source-bound manifests and the readiness audit. No reviewer agreement result is included in this CI evidence registry. |
| VIS-01 | Board colour accuracy against ground truth | BLOCKED | [source-pixel audit limits](SOURCE_PIXEL_AUDIT.md), `data/vision_level39.json` | Obtain independent labels for genuine captures, evaluate across representative boards/devices, report per-class metrics and uncertainty, and keep calibration alignment separate from colour-label agreement. |
| SHO-01 | Shooter visibility, slot, colour and ammunition accuracy | BLOCKED | [shooter evaluation guide](SHOOTER_OBSERVATION_EVALUATION.md), `shooter_detector.py`, review tools | Obtain independent human labels across captures and panel conditions; evaluate visibility, position, colour and OCR separately. The fixed 3×4 layout and top-row OCR assumptions remain limitations until validated. |
| CON-01 | Conveyor identity and timing | PARTIAL | `conveyor_simulator.py`, `conveyor_timeline.py`, `conveyor_consistency_auditor.py`, [integration guide](CAPTURE_SIMULATOR_INTEGRATION.md) | Compare model state/timing with genuine multi-frame observations and document which mechanics are confirmed versus assumed. Fixture/CI agreement is not live-game validation. |
| SOL-01 | Solver correctness and completeness | PARTIAL | `game_state.py`, `solver.py`, `execution_engine.py`, `test_game_state_validation.py`, `data/solver_reference_cases.json`, `test_solver_reference_cases.py`, [solver validation reference](SOLVER_VALIDATION_REFERENCE.md) | Structural input rejection, direct shot-API validation and eleven hand-checkable ray cases covering all four cardinal directions now have regression coverage, and the fixture schema is checked for exact field sets and types. Still build an independently verified reference corpus for every supported mechanic, including solved, unsolved, ambiguous and invalid states; verify bounds, resource constraints and heuristic limitations. Do not claim global optimality without proof. |
| DEV-01 | Termux installation and target-device execution | BLOCKED | `deploy_termux.sh`, `build_pipeline.sh`; CI shell-syntax check | Run on the actual supported Android/Termux environment and preserve a dated report with Android version, Termux version, Python/dependency versions, commands, exit codes, timings and artifact hashes. Shell syntax in GitHub CI is not a device run. |
| PKG-01 | Release/package validation | NOT VERIFIED | `deploy_termux.sh`, `requirements.txt` | Decide the supported release format (Termux source deployment unless the scope changes), run a clean install from documented dependencies, and archive the reproducible build/install report. No APK is claimed. |
| SEC-01 | Dependency and secret-handling audit | NOT VERIFIED | `requirements.txt`, `.gitignore`, deployment scripts | Record dependency versions, vulnerability review date, secret scan result and local-data handling. Never put tokens, private screenshots or account data into public evidence. |
| E2E-01 | Screenshot-to-dry-run recommendation path | PARTIAL | `capture_pipeline.py`, `capture_preflight.py`, `orchestration.py`, [integration guide](CAPTURE_SIMULATOR_INTEGRATION.md) | Reproduce the full offline flow from a real capture through preflight, state loading, synchronization, solver diagnostics and report generation; archive exact input/output hashes and blockers. |

## CI evidence snapshot

The verified CI runs are recorded machine-readably in [`evidence/final/ci_runs.json`](../evidence/final/ci_runs.json). The latest listed run (#1176) passed **1,225 unit tests on each of Python 3.10, 3.11, 3.12 and 3.14**, along with Python compilation and Termux build-script syntax checks.

These runs were triggered for stacked pull requests. They are **not** tests on an Android handset, do not establish detector accuracy, and do not verify gameplay.

At the time of this audit, PRs #138–#142 are open draft PRs in a feature-branch stack. They are not merged into `main`. See [the audit report](FINAL_COMPLETION_AUDIT.md) for the exact scope and outstanding external blockers.

## Definition of 100% completion

Do not mark 100% until all in-scope criteria are either verified or explicitly excluded by an approved scope decision:

1. All feature PRs have received human review, required CI is green on the final integrated branch, and the final branch has no unreviewed stacked changes.
2. A clean deployment has been completed on the target Termux/Android environment; the report records versions, commands, results, errors and hashes.
3. Independent human review datasets are complete and source-bound. Reviewer labels are not copied from detector output; ambiguous records remain explicit; agreement and per-class coverage are reported.
4. Board, shooter and conveyor metrics are calculated from genuine captures and independently reviewed labels. Confidence intervals and sample limitations are documented.
5. The solver has a hand-checked reference set for every supported mechanic and clearly rejects unsupported or ambiguous rules.
6. The offline end-to-end path is reproducible from original capture bytes to the final diagnostic/dry-run report, with all artifact hashes linked.
7. Dependency/security review and release/install documentation are complete.
8. Known limitations, external blockers and unsupported mechanics are listed in the final report. No false claim of gameplay verification, real-device success, 100% accuracy or global optimality is made.

**Safety invariant:** all final work remains offline/advisory. `game_taps_enabled`, `live_execution_allowed` and purchase automation must remain false. No live-game action is part of this completion checklist.
