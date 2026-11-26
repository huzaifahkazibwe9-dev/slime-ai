# Paired shooter-review intake readiness audit

Use this preflight after generating a paired blank review pack and while the
two reviewers complete their files. Unlike the agreement evaluator, this tool
accepts unfinished datasets and reports per-reviewer completion progress.

## Run

Generate the pair from the exact detector JSON and screenshot:

```text
python prepare_shooter_review_pair.py detection.json original_screenshot.png \
  --output-dir data/review-pair \
  --reviewer-a-id reviewer-a \
  --reviewer-b-id reviewer-b
```

Check progress at any time:

```text
python shooter_review_intake_audit.py data/review-pair/review_manifest.json \
  --reviewer-a-id reviewer-a \
  --reviewer-b-id reviewer-b \
  --output data/shooter_review_intake_audit.json
```

The report shows reviewed, confirmed, ambiguous, and not-yet-reviewed slot
counts for each reviewer, plus a completion rate for each dataset. Ambiguous
slots count as reviewed only when their human fields remain blank. A dataset
is complete only when all slots are confirmed or ambiguous and
labelled_by_user is true.

## Source and dataset checks

For every manifest entry, the audit rebuilds the expected blank template from
the exact detector JSON bytes and original screenshot bytes. It rejects
changed detector snapshots, altered source/template metadata, malformed human
labels, prefilled labels on unreviewed slots, duplicate capture sessions,
repeated screenshot bytes, and reused reviewer dataset files. Dataset
fingerprints are SHA-256 hashes of the exact file bytes.

The report sets agreement_audit_ready to true only when both datasets are
complete for every listed capture. Then run
shooter_batch_review_agreement.py to calculate reviewer-to-reviewer
agreement.

This preflight does not authenticate reviewer IDs, prove that two people
worked independently, establish label truth, calculate agreement, verify
detector accuracy, or verify gameplay. Its readiness flag only means the
paired files are complete and source-bound. game_taps_enabled remains false.

To make completeness a hard gate for an automated pipeline, add
`--require-ready`:

```text
python shooter_review_intake_audit.py data/review-pair/review_manifest.json \
  --reviewer-a-id reviewer-a \
  --reviewer-b-id reviewer-b \
  --output data/shooter_review_intake_audit.json \
  --require-ready
```

The command always saves the report first. It exits with status `0` when all
reviewers have completed all captures, and status `1` when any slot remains
unreviewed. Without `--require-ready`, an incomplete but valid intake remains
a successful audit and returns status `0`, so progress can be checked
repeatedly without treating work-in-progress as corrupt evidence.
