# Human-reviewed shooter observation evaluation

This workflow measures agreement between Slime AI's shooter-panel detector and
labels entered by a human reviewer. It covers four separate questions:

1. **Visibility:** does the detector's fixed row assumption agree with what is
   actually visible at each calibrated panel location?
2. **Slot-position alignment:** does the detector's sampled coordinate land in
   the row and column identified by the reviewer?
3. **Colour:** does the fixed HSV colour label agree with the reviewer's label?
4. **Ammunition:** does Tesseract's exact-digit reading equal a legible
   human-reviewed ammunition count?

The tool does not change thresholds or detector calibration. It does not
enable game actions.

## Source binding and template review

The template builder requires both the detector JSON and the exact original
screenshot used to produce it. The screenshot's SHA-256 must match
capture_provenance.source_sha256, and the detector capture provenance must be
explicitly verified. The detector JSON is also fingerprinted byte-for-byte.

Each of the 12 calibrated panel locations receives a separate record. Detector
outputs are retained under the detector field; all human fields start blank
under human. The builder does not copy predicted colour or ammunition into
human labels. The template also retains the panel bounds, panel image
dimensions, source screenshot dimensions, capture session, capture timestamp
and capture configuration digest.

Review every coordinate against the original screenshot. The stored
screen_center, screen_box and screen_sample values are in the detector's
resized panel-crop coordinate system, not full-screen phone coordinates. The
original screenshot and recorded panel bounds provide the reference image.
Do not use a colour or ammunition prediction as its own reference label.

For every sample set review_status to one of:

- confirmed: the reviewer can make the requested assessment.
- ambiguous: the location was inspected but cannot be labelled confidently.

Do not leave not_reviewed records when marking the dataset ready.

For a confirmed sample, set human.visibility to one of visible, unrevealed,
partially_occluded, or empty. Record the actual one-based row and column where
the detector's sample coordinate lands; use null for both when it does not
land on a panel slot.

For visible samples, fill human.colour using one of the exact detector labels:
black, white, gray, red, brown, orange, yellow, green, cyan, blue, purple, or
magenta. Set human.ammunition_readable to true only when the number is legible
and enter the non-negative integer in human.ammunition. When it is not
legible, set human.ammunition_readable to false and leave human.ammunition as
null.

For non-visible samples, leave colour blank, set ammunition readability to
false, and leave ammunition as null.

After manually reviewing every record, change the top-level labelled_by_user
field to true. This is an explicit declaration that the human review was
completed, not cryptographic proof of label accuracy.

## Metrics and interpretation

The report includes:

- Visibility accuracy and a confusion matrix over all confirmed samples.
- Slot-position alignment accuracy for confirmed samples with a human row and
  column. This evaluates fixed coordinate alignment, not shooter identity
  tracking over time.
- Colour accuracy and a confusion matrix for samples reviewed as visible.
- Ammunition exact-match accuracy, count of missing detector readings, and
  mean absolute error among readings the detector did produce. A missing OCR
  result counts as an incorrect result when the reviewer says ammunition was
  legible.
- Counts of ambiguous samples, reviewed visibility classes, and detector
  sample-quality statuses.

The current detector's readable_candidate, unrevealed_candidate, and
partially_occluded_candidate statuses are derived from fixed row assumptions.
They are not independent object-presence detections. Visibility scoring
therefore measures whether those assumptions match a human review; it does not
turn the fixed-slot approach into a general detector.

Slot-position scoring checks whether calibrated sampling coordinates align
with human-identified panel positions. It does not verify persistent shooter
identity or prove the panel bounds are correctly calibrated for every device.

Colour and ammunition scores describe agreement on the reviewed subset.
Coverage adequacy is not automatically assessed. A useful estimate requires
multiple genuine captures, varied board/panel conditions, careful review of
ambiguous cases, and sufficient examples across colours and ammunition values.
Do not infer live gameplay success from a high score on a small sample.

## Source verification

The evaluation command requires the completed dataset, the original detector
JSON and the original screenshot. It verifies:

- the detector JSON byte hash;
- the original screenshot byte hash and decoded dimensions;
- capture metadata consistency;
- the full detector observation snapshot retained in the template.

If a dataset's detector snapshot is edited after template creation, source
verification rejects it. Human labels remain user-supplied and are not
independently verified by these checks.

All reports explicitly retain:
label_truth_independently_verified = false,
slot_mapping_independently_verified = false,
colour_independently_verified = false,
ammunition_independently_verified = false,
gameplay_verified = false, and game_taps_enabled = false.

This is an offline evaluation path only. It does not perform device actions,
purchase power-ups, select shooters, or modify the game.


## Multi-capture aggregation

For a more representative evaluation, review multiple different captures and
aggregate their labelled records with shooter_batch_evaluation.py. Its JSON
manifest has schema version 1 and a captures list. Each entry supplies three
paths: dataset, detection, and screenshot. Paths that are not absolute are
resolved relative to the manifest file's directory.

The batch evaluator independently verifies every dataset against its exact
detector JSON and original screenshot before including it. It rejects repeated
capture sessions, identical source detector files, and duplicate screenshot
bytes so the same screenshot cannot inflate the sample count. Reports retain
per-capture results as well as support-weighted aggregate visibility, slot
alignment, colour, and ammunition metrics.

A combined report still does not prove that human labels are correct or that
the captures represent every gameplay condition. Coverage adequacy and label
truth remain explicitly unverified.



### Descriptive coverage profile

Both the single-capture evaluator and multi-capture batch evaluator include a
`coverage_profile` using the same schema. The batch report provides it at
both aggregate and per-capture levels. It reports confirmed versus ambiguous
review counts for each of the 12 detector panel coordinates, human-labelled
visibility-class support, visible colour-class support, legible ammunition
value counts, and visible detector sample-quality/OCR-status counts. This
makes missing positions or unrepresented classes visible before interpreting
accuracy metrics.

Panel-position counts use the detector's nominal calibrated slot coordinates.
They describe which slots were reviewed, not independent proof that the
detector sampled the correct physical positions. Class and ammunition counts
describe only the reviewed samples. No statistical minimum-support threshold
is imposed and no representativeness test is claimed;
`coverage_adequacy_assessed` remains false. Use these counts to plan
additional captures and reviews, not as a deployment or gameplay gate.

Both report types also include an advisory `review_follow_up` section;
the batch report provides it at aggregate and per-capture levels. It lists
panel positions with no confirmed review, positions containing ambiguous
samples, visibility classes with zero confirmed support, and visible colour
classes with zero confirmed support. Use these lists to decide what to inspect
next. A zero-support class is an observed absence in the supplied review set,
not proof that the class must appear in the next capture. No sample quotas are
imposed, and this section does not alter
`coverage_adequacy_assessed = false`.

## Two-reviewer agreement audit

For an additional consistency check, use
`shooter_review_agreement.py` to compare two separately completed review
datasets from the same original screenshot. The tool verifies both datasets
against the exact detector JSON and screenshot bytes, then reports agreement
by review status, visibility, panel position, colour, ammunition readability,
and exact ammunition value. It also lists sample-level disagreements.
Agreement support is limited to samples eligible for each field; the report
does not infer missing comparisons.

This is a consistency audit, not a truth audit. Caller-supplied reviewer IDs
are not authenticated, and agreement does not establish label correctness or
reviewer independence. See
[`docs/TWO_REVIEWER_AGREEMENT.md`](TWO_REVIEWER_AGREEMENT.md) for the workflow,
denominators, CLI options, and interpretation limits. Gameplay and game taps
remain disabled.

## Ammunition OCR status diagnostics

The detector now records a structured status beside each ammunition result.
A successful exact-digit parse is marked PARSED_EXACT_DIGITS. Other statuses
distinguish TESSERACT_UNAVAILABLE, TESSERACT_TIMEOUT, TESSERACT_PROCESS_ERROR,
TESSERACT_EXECUTION_ERROR, TESSERACT_NONZERO_EXIT,
INVALID_TESSERACT_OUTPUT, AMBIGUOUS_OR_NON_INTEGER_OUTPUT, NUMBER_TOO_LONG,
and other process/conversion failures. Unrevealed or partially occluded rows
are marked NOT_ATTEMPTED_UNVERIFIED_SLOT rather than being described as OCR
failures.

The template retains the detector status separately from the human-reviewed
number. Evaluation reports include per-sample OCR status and counts by status
for visible samples; batch reports aggregate those counts across captures.
These diagnostics help distinguish missing OCR from ambiguous readings, but
do not prove a correctly parsed number is accurate. Human comparison against
legible source screenshots remains necessary.


## Runtime gate for ammunition OCR failures

Current detector records declare structured OCR quality metadata. The runtime
shooter loader now requires every visible shooter in such a record to carry
`ammo_observation_status=PARSED_EXACT_DIGITS` and a non-negative integer count.
Missing status, timeout, unavailable OCR, ambiguous output, or a success status
without a count blocks loading rather than allowing a partial or stale shooter
state into planning. Legacy records without detector quality metadata retain
compatibility behavior and are explicitly marked legacy/unverified.

The loaded shooter state and simulator snapshots also preserve the OCR status.
A detector-declared state is rejected if its status is missing or is not
`PARSED_EXACT_DIGITS`; the level audit reports counts by OCR status. This keeps
a failed OCR state from becoming valid merely by passing through a simulation
snapshot/restore cycle.
