# Two-reviewer shooter-label agreement audit

This offline tool compares two separately completed human-review datasets for
the **same exact capture**. It measures reviewer-to-reviewer consistency; it
does not decide which reviewer is correct.

## Prepare the two reviews

Create two independent copies of the blank template from the same original
detector JSON and screenshot. Each reviewer should inspect the original
screenshot and complete their own copy without seeing or copying the other
reviewer's labels. Each dataset must have `labelled_by_user = true`, and every
panel position must be marked `confirmed` or `ambiguous`.

The audit accepts two caller-supplied reviewer identifiers. Use distinct,
non-identifying labels such as `reviewer-a` and `reviewer-b`. The tool does
not authenticate these identifiers or prove that two different people
completed the files.

## Run the audit

The command accepts both labelled datasets and the exact detector and
screenshot files they came from:

```text
python shooter_review_agreement.py reviewer_a_labels.json reviewer_b_labels.json \
  --reviewer-a-id reviewer-a \
  --reviewer-b-id reviewer-b \
  --source-detection detection.json \
  --source-screenshot original_screenshot.png \
  --output data/shooter_review_agreement.json
```

Both datasets are validated and independently source-checked against the
provided detector JSON and screenshot bytes. A changed detector observation,
mismatched screenshot, or different capture session is rejected.

## Agreement fields and denominators

The report provides support, exact agreement count, agreement rate, and
nominal Cohen's kappa where defined for:

- **Review status:** confirmed versus ambiguous, across all 12 positions.
- **Visibility:** compared only where both reviewers marked the sample
  confirmed.
- **Panel position:** compared on the same jointly confirmed samples. A
  reviewer assigning no panel position is represented as a null position.
- **Colour and ammunition readability:** compared only where both reviewers
  marked the sample confirmed and visible.
- **Exact ammunition value:** compared only where both reviewers marked the
  sample visible and the ammunition legible.

For each disagreement, the JSON report records the detector sample ID, field,
and both supplied values. In addition to aggregate metrics, the
`per_slot_agreement` object reports row, column, support, agreement rate, and
Cohen's kappa status for each detector slot. This prevents a strong aggregate
score from hiding disagreement concentrated in one panel position. A field
with no eligible comparisons reports null agreement. Cohen's kappa is null
when its expected-agreement denominator is zero; `cohen_kappa_status`
explains why.

## Interpretation and limitations

Agreement is not accuracy. Two reviewers can agree and both be wrong. Reviewer
identifiers are plain caller-supplied labels; independence is not verified.
The audit does not verify label truth, detector correctness, slot calibration
on another device, representativeness, or gameplay performance. It does not
alter detector thresholds, calibrate the model, interact with the game, or
enable game taps.

The report explicitly keeps
`reviewer_independence_verified = false`,
`label_truth_independently_verified = false`,
`gameplay_verified = false`, and `game_taps_enabled = false`.
