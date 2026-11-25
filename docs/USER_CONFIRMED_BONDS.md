# User-confirmed bonded shooter groups

The detector reads `data/bonded_groups_confirmed.json`. The build pipeline
creates a blank unverified template when this file is absent. It never inserts
pairs inferred from colour or panel position and never overwrites an existing
file.

## Template format

```json
{
  "verified_by_user": false,
  "bonded_groups": [],
  "template_only": true
}
```

After checking the current screenshot and the detector's visible shooter IDs,
edit the file to list only groups that you have independently confirmed. For
example, this is a format illustration, not a claim about the current game
state:

```json
{
  "verified_by_user": true,
  "bonded_groups": [
    ["top_1", "top_2"],
    ["top_3", "top_4"]
  ]
}
```

## Validation rules

- `verified_by_user` must be the JSON boolean `true`.
- Each group contains two or three unique, currently detected shooter IDs.
- A shooter cannot appear in more than one group.
- Every referenced ID must exist in the current `shooter_detection.json`.
- Group edges must be reciprocal in the detector output.
- The detector fingerprints the exact config bytes and carries the digest and
  source label into its output.
- The candidate matcher re-reads the config and requires its bytes, digest,
  declared groups and detector output to agree.
- Orchestration, the planner and `STATUS` pin this file's digest. Changing the
  config invalidates candidate reports and saved plans until the capture and
  planning pipeline are regenerated.

A blank or unconfirmed config does not enable bonded-group planning. The
software does not infer bonds from matching colours, position, or visual
similarity. Confirm groups only after checking the actual game evidence.

Bond confirmation verifies the physical grouping only. It does not verify
colour mapping, ammunition OCR, firing, gameplay success, or authorise any
device action. Live game taps and power-up purchases remain disabled.
