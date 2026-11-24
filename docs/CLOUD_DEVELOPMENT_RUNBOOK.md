# Cloud development runbook

This repository can be worked on by a compatible cloud coding agent while the owner's phone is offline. The agent runs in the provider's cloud environment, not inside ChatGPT or Termux.

## What this repository provides
- `AGENTS.md`: project-specific coding, testing, and safety instructions.
- `.github/workflows/tests.yml`: existing CI for pushes, pull requests, manual dispatch, and a daily scheduled test run.
- Draft pull requests: the review boundary for proposed code changes.

These files do **not** themselves provision an AI agent or guarantee continuous 24/7 work. A supported cloud coding-agent service, repository authorization, and an explicitly started/assigned task are still required. Provider availability, session limits, quotas, and requests for human input can pause work.

## Safe operating procedure
1. A human reviews the task and provides a narrow, testable objective.
2. The cloud agent reads `AGENTS.md` and works on a feature branch.
3. The agent runs the relevant tests and the full repository test suite.
4. The agent opens a draft PR against `main`, including test evidence and known limitations.
5. CI runs on the PR. A human reviews the diff, CI results, and safety implications.
6. Only a human may authorize merging. No agent may deploy to the phone or interact with the live game.

## Current bounded work queue
Use these as candidate tasks only after reviewing the latest repository and open PR state. Do not assume historical branch or CI status is still current.

1. Review the consuming-state semantics in `dynamic_board_simulator.py` and `bonded_group_simulator.py`. Verify mutation contracts, final-board/ammunition coherence, and report fields with regression tests.
2. Audit shooter-panel geometry and confidence handling. Preserve the rule that unverified rows and low-confidence samples are not selectable. Do not describe fixed sample points as circle detection.
3. Add reproducible host-side benchmarks for screenshot ingestion and simulation hot paths. Keep device performance and battery claims explicitly unverified until measured on the actual phone.
4. Review bonded-group observation and planning invariants with fixture-backed tests. Incomplete groups must remain withheld.
5. Perform an integration review across open PRs before proposing any combined change. Do not merge or rewrite existing PRs without explicit authorization.

## Required completion report
Every task report must state:
- task and branch;
- files changed;
- exact tests and commands run;
- pass/fail results from the actual run;
- CI run link or an explicit statement that CI is pending/not available;
- assumptions, unresolved risks, and required human/device validation;
- draft PR link.

## Limits
The daily scheduled workflow is a test run, not an autonomous AI coding loop. It does not write code, assign issues, or create PRs by itself. Do not add API keys or paid agent services to repository secrets without explicit owner approval and appropriate account-holder review.
