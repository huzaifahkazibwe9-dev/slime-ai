# Multi-capture two-reviewer agreement audit

This workflow aggregates two-reviewer consistency across a set of distinct,
source-bound shooter screenshots. Each manifest capture contains two completed
human-review datasets, the exact detector JSON, and the original screenshot.

## Generate a paired blank-review pack

To avoid accidental copying of labels between reviewers, generate the two
separate blank templates from one verified detector JSON and screenshot:

```text
python prepare_shooter_review_pair.py detection.json original_screenshot.png \
  --output-dir data/review-pair \
  --reviewer-a-id reviewer-a \
  --reviewer-b-id reviewer-b
```

The command writes `reviewer-a.json`, `reviewer-b.json`, and
`review_manifest.json`. Both templates start with blank human labels and
`labelled_by_user = false`; the source hashes and detector snapshot match.
Existing files are not overwritten unless `--overwrite` is explicitly
provided. Reviewer IDs are filename-safe labels, not authenticated identities.

Give each blank dataset to its respective reviewer. Each reviewer must complete
their file independently against the original screenshot before running the
agreement audit.

## Manifest

Create a UTF-8 JSON manifest:

```json
{
  "schema_version": 1,
  "captures": [
    {
      "reviewer_a_dataset": "capture-01-reviewer-a.json",
      "reviewer_b_dataset": "capture-01-reviewer-b.json",
      "detection": "capture-01-detection.json",
      "screenshot": "capture-01.png"
    },
    {
      "reviewer_a_dataset": "capture-02-reviewer-a.json",
      "reviewer_b_dataset": "capture-02-reviewer-b.json",
      "detection": "capture-02-detection.json",
      "screenshot": "capture-02.png"
    }
  ]
}
```

Paths are resolved relative to the manifest directory unless absolute. Every
dataset must be completed and independently source-bound to its matching
detector JSON and screenshot. The tool rejects duplicate capture sessions and
repeated screenshot bytes.

## Run

```text
python shooter_batch_review_agreement.py review_manifest.json \
  --reviewer-a-id reviewer-a \
  --reviewer-b-id reviewer-b \
  --output data/shooter_batch_review_agreement.json
```

## Report

The report includes pooled exact-agreement counts and rates for review status,
visibility, panel position, colour, ammunition readability, and exact
ammunition values. It includes per-slot pooled agreement, per-capture reports,
and sample-level disagreements. Each field retains its own eligible support
denominator. Every per-capture report also retains the SHA-256 hashes of both
reviewer dataset inputs. Batch CLI reports use exact file-byte hashes and
verify that those bytes parse to the supplied dataset objects.

Cohen's kappa remains available in each per-capture report. The top-level
aggregate does not average kappa values: a weighted average of per-capture
kappa is not equivalent to computing kappa from pooled reviewer contingency
counts. The aggregate explicitly sets kappa to null with
`cohen_kappa_status = not_pooled_across_captures`.

Reviewer identifiers are caller-supplied and not authenticated. Agreement is
not accuracy; this workflow does not establish reviewer independence, label
truth, detector quality, representativeness, or gameplay success. It does not
change detector calibration or interact with the game. Game taps remain
disabled.

## Check completion before agreement

While reviews are still in progress, run
`shooter_review_intake_audit.py review_manifest.json` with the same two
reviewer IDs. The preflight verifies that both datasets remain tied to each
exact capture and reports confirmed, ambiguous, and not-yet-reviewed counts.
It accepts unfinished datasets and sets `agreement_audit_ready = true` only
when both reviewers have completed every slot in every capture. See
[`REVIEW_INTAKE_READINESS.md`](REVIEW_INTAKE_READINESS.md) for the full
preflight command and validation rules.
