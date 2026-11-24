# Board-colour calibration and evaluation

Slime AI's board-colour classifier is a fixed HSV-threshold function. This tool
measures how often it agrees with a reference set of RGB samples whose labels
were supplied by a human reviewer.

## Prepare a review template

After running screenshot ingestion on a complete screenshot, create a template
from its observation JSON:

```sh
python prepare_colour_labels.py data/board_observation_latest.json
```

The template contains each sampled RGB value and its zero-based board row and
column. It deliberately leaves every label blank and sets
`labelled_by_user` to `false`. Review the original screenshot, fill every
sample's `label` with the human-identified colour, and only then change
`labelled_by_user` to `true`. Do not use the classifier's predicted board
labels as reference labels. Keep the original screenshot available for review.

Run the evaluator only after completing that manual review:

```sh
python vision_calibration.py data/colour_labels_template.json --source-image path/to/original-screenshot.jpg
```

## Dataset format

The evaluator accepts a UTF-8 JSON file with this structure:

```json
{
  "schema_version": 1,
  "labelled_by_user": true,
  "samples": [
    {"id": "level39-cell-r03-c07", "rgb": [104, 195, 233], "label": "cyan"},
    {"id": "level39-cell-r03-c08", "rgb": [245, 245, 245], "label": "white"}
  ]
}
```

Each sample needs a unique, non-empty ID, exactly three integer RGB channels
from 0 through 255, and a non-empty reference label. Templates also carry the
source screenshot SHA-256, image dimensions, grid dimensions, and each sample's
zero-based row/column. The evaluator preserves this provenance in its report
and validates grid coordinates. When `--source-image` is supplied, the
evaluator hashes that file and refuses to score the dataset if it is not the
exact screenshot recorded in the template. This binds the report to a source
file; it does not verify that the human labels are correct. The explicit
`labelled_by_user` flag is required so automatically generated predictions
cannot silently be treated as ground truth.

## Labelling protocol

- Read RGB values from the original screenshot, not from the classifier's
  predicted label.
- Assign the label by visually checking the corresponding in-game tile and
  the agreed colour name.
- Use the classifier's exact canonical spellings: `dark`, `white`, `gray`,
  `red`, `orange`, `yellow`, `green`, `cyan`, `blue`, `purple`, or `pink`.
  Do not mix aliases such as `grey`/`gray`; the evaluator compares labels
  exactly and treats different spellings as different classes.
- Include examples from different levels, board regions, tile shades, and
  screenshot conditions. Do not create a dataset by copying predicted labels.
- Keep ambiguous samples out until a reviewer can resolve them; record them
  separately rather than guessing.
- Keep sample IDs traceable to the screenshot and cell without embedding
  unnecessary personal information.

## Metrics

The report includes overall accuracy, a confusion matrix, and per-class
precision, recall, F1, support, and predicted count. Macro recall helps expose
classes that perform poorly even when they are less common.

The evaluator does not tune thresholds or alter the classifier. It also does
not claim that human labels are independently verified, that the dataset
represents every game condition, or that gameplay behaviour has been proven.
A useful calibration decision requires a sufficiently broad, carefully
reviewed dataset and human inspection of confusion cases.

All gameplay verification and live game actions remain disabled.

 
## Coverage audit

Every evaluation report also includes a descriptive `coverage` section:

- `class_sample_counts` counts human-assigned examples for every canonical colour.
- `missing_classes` lists colours with no labelled examples.
- When template grid coordinates are present, `spatial_regions` reports sample and
  per-colour counts in the four board quadrants; `empty_spatial_regions` identifies
  quadrants with no samples.
- For hand-authored datasets without grid metadata, class counts remain available
  and spatial coverage is explicitly marked unavailable.

Quadrants are a coarse sampling diagnostic, not a guarantee of representative
coverage. Counts do not establish sample independence, shade diversity, level
diversity, or label correctness. The report deliberately sets
`coverage_adequacy_assessed` to `false`; reviewers must decide whether the dataset
is broad enough for a meaningful evaluation.
