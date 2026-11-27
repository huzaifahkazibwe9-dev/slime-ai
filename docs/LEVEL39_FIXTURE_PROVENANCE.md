# Level 39 structured fixture provenance

These files are a narrow port of the JSON fixtures published on the historical
`publish-level39-evidence` branch (PR #123, source head
`401deba5c5b62f0d675d7a89cc278e64ddd86fc8`). Only the seven JSON data files
are ported; the historical branch contains unrelated, divergent code history
and is not used as this branch's base.

## What these files contain

- `vision_level39.json`: a 35 × 35 labelled board and per-cell RGB samples.
- `shooter_detection.json`: four visible shooter-panel candidates, their
  observed colour/ammunition fields, and two user-labelled bonded groups.
- `color_matches.json`: four visual colour candidates, explicitly not
  gameplay-verified.
- `conveyor_calibration.json`: eight calibrated conveyor positions and
  directions, marked user-verified in the source fixture.
- `conveyor_visual_observations.json`: eight position-based observations
  attributed in the source JSON to a visual contact sheet.
- `conveyor_timeline.json`: regenerated with the current
  `conveyor_timeline.build_timeline` layout. Sequence confirmation is false
  because this port does not infer a new explicit confirmation.
- `conveyor_consistency_report.json`: regenerated with the current
  `conveyor_consistency_auditor.audit` output schema.

## Evidence limits

This PR contains structured JSON, not original screenshot files. The source
fixtures do not provide independently verified capture timestamps or physical
shooter identities. The position/ammunition series can be checked for internal
consistency, but that does not prove that a particular physical shooter moved
between positions or that the game's live conveyor mechanics behave as
simulated.

The following flags remain false: gameplay verification, gameplay taps, and
physical shooter identity. A green data-integrity test is not a gameplay
accuracy claim, not solver-optimality evidence, and not a device-validation
result. Do not remove these limits or label these records as fresh captures.
