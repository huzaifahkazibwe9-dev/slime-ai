# Slime AI agent instructions

These instructions apply to any AI coding agent working in this repository, including cloud coding agents.

## Mission
Improve the Slime Loop screenshot-analysis, planning, simulation, and diagnostics code. Prefer small, independently testable changes. Do not claim completion without evidence.

## Required workflow
1. Read this file, the relevant module documentation, current tests, and the active pull-request context before editing.
2. Work only on a dedicated feature branch. Never commit directly to `main`.
3. Select one bounded task from the current approved issue or task request. Do not invent broad product requirements.
4. Inspect call sites and invariants before changing behavior. Add regression tests for every bug fix.
5. Run the narrow relevant tests, then the full suite with `python -m unittest discover -v`; run `python -m compileall -q .` as well.
6. Report exact commands, test outcomes, files changed, limitations, and any unverified assumptions.
7. Open a **draft** pull request against `main`. Keep each PR focused and explain its risk and rollback path.
8. Stop after opening the draft PR. A human must review and explicitly authorize merging.

## Non-negotiable safety constraints
- Never add or enable live game taps, automated gameplay input, purchases, spending, or automatic power-up use.
- Keep execution in simulation/dry-run mode. Do not weaken existing safety gates, evidence checks, provenance checks, or confidence thresholds to make a test pass.
- Never infer shooter identity, ammunition, bonds, or selectability from unverified screen regions. Unknown or incomplete observations must fail closed.
- Do not fabricate screenshots, measurements, benchmarks, test results, gameplay wins, battery savings, or device validation.
- Do not overwrite user data, local captures, calibration files, or ignored runtime state.
- Do not introduce secrets, tokens, passwords, personal data, paid services, or new external dependencies without explicit human approval.
- Do not change GitHub permissions, repository settings, branch protection, secrets, or workflows to grant broader access.
- Never merge PRs, close unrelated PRs, or modify `main`.

## Engineering standards
- Preserve backward compatibility unless the task explicitly authorizes a breaking change.
- Prefer deterministic tests and fixtures. Keep real-device validation separate from CI claims.
- For state-consuming optimizations, verify mutation semantics, final-state coherence, and source-state integrity claims.
- For vision changes, distinguish heuristic confidence from actual object/circle detection and use complete screenshot-backed evidence.
- For performance work, provide reproducible before/after benchmarks; do not infer speedups from code inspection alone.
- Keep dependencies minimal and pin or constrain them consistently with the existing project.

## When blocked
Stop rather than guess if the task needs credentials, paid resources, human confirmation, unavailable screenshots, unclear gameplay rules, or a safety-sensitive behavior change. Open or update a draft PR only when there is a safe, testable partial result; otherwise report the blocker without changing code.
