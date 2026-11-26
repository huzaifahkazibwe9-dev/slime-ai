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

A completed review pair is not automatically eligible for the agreement
evaluator. Each reviewer must have at least one `confirmed` sample in every
capture; the evaluator rejects a dataset containing only ambiguous samples.
The intake report exposes this distinction through each reviewer's
`agreement_eligible` flag and lists per-capture blockers in
`readiness_blockers`.

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

The command always saves the report first and prints a per-capture blocker
summary to the terminal. It writes through a uniquely named temporary file in
the output directory and atomically replaces the report, so an existing
`*.tmp` file is not reused. On POSIX systems, the final report keeps the
private `0600` permissions of the temporary file. If opening the temporary
file stream fails, the raw file descriptor and partial file are also cleaned
up. It also prints
confirmed, ambiguous, and unreviewed counts separately for both reviewers in
every capture. Unreviewed
slots and
the absence of a confirmed sample are reported separately for each reviewer.
It exits with status `0` only when
every reviewer has completed every slot and has at least one confirmed sample
in every capture. It exits with status `1` when a slot remains unreviewed or a
reviewer has no confirmed sample for a capture. Without `--require-ready`, a
valid but incomplete or agreement-ineligible intake remains a successful
progress audit and returns status `0`. The JSON report remains the complete
machine-readable source of blocker details.
