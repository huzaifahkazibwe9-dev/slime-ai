# Evidence contracts for skipped public tests

These tests stay skipped until the listed local files exist and match the
assertions already in the test modules. Do not invent Level 39 screenshots,
ammunition series, capture IDs, or annotations to make them pass. Synthetic
offline tests live in `test_conveyor_synthetic_offline.py` and use a different
capture id (`synthetic-offline-not-a-game-capture`) and different ammunition
numbers on purpose.

Files below are gitignored local evidence. Paths are relative to the
repository root. JSON must be UTF-8. Safety flags named here must stay false;
a file that flips them true would fail the existing tests and must not be
treated as permission to enable taps.

## `test_colour_mapping_auditor.py` — `test_actual_level39_data`

Required files, all present:

- `data/vision_level39.json`
- `data/shooter_detection.json`
- `data/color_matches.json`

`colour_mapping_auditor.audit` must return exactly four results whose
`best_candidate` values are, in shooter order, `white`, `cyan`, `purple`,
`orange`. The auditor reads `board`, `raw_rgb`, and `grid_size` from the
vision file; `visible_shooters[].id` plus `color.name` and `color.rgb` from
the shooter file; and `mappings[shooter_id].board_colour` / `status` from the
colour-match file.

## `test_vision_validator.py` — `test_actual_level39_data`

Required file: `data/vision_level39.json`.

`vision_validator.audit_data` must report `grid_size` `[35, 35]`,
`valid_rgb_samples` `1225`, `classification_mismatch_count` `0`, and
`saved_counts_match` true. That implies a 35 by 35 `board`, a matching
`raw_rgb` sample grid, and `counts` that agree with the labelled cells.

## `test_conveyor_timeline.py`

Required files, both present:

- `data/conveyor_timeline.json`
- `data/conveyor_visual_observations.json`

Timeline object:

- `sequence`: `["bottom", "right", "top", "left"]`
- `snapshots`: length 4
- `candidate_tracks.white.ammo`: `[38, 33, 26, 26]`
- `candidate_tracks.blue_cyan.ammo`: `[40, 27, 18, 0]`
- `identity_verified`: false
- `gameplay_taps_enabled`: false
- `timestamps_known`: false

Each snapshot has `white_candidate` and `blue_cyan_candidate`. Each of those
objects must be exactly equal to the observation in
`conveyor_visual_observations.json` whose `position_id` matches, under
`observations` (a list of objects that include `position_id`).

The public builder in `conveyor_timeline.py` can arrange observations into
this shape, but it does not create the private ammunition series. It records
`sequence_confirmed_by_user` only when `--confirm-sequence` is passed.

## `test_conveyor_consistency.py`

Required file: `data/conveyor_consistency_report.json`.

- `overall_status`: `CONSISTENT_CANDIDATE_DATA`
- `candidate_tracks.white.ammunition`: `[38, 33, 26, 26]`
- `candidate_tracks.white.positions`: `["bottom_1", "right_2", "top_2", "left_1"]`
- `candidate_tracks.blue_cyan.ammunition`: `[40, 27, 18, 0]`
- `candidate_tracks.blue_cyan.positions`: `["bottom_2", "right_1", "top_1", "left_2"]`
- `identity_verified`: false
- `gameplay_taps_enabled`: false

`conveyor_consistency_auditor.audit` can produce this shape from a timeline
plus the original observations. A passing synthetic audit is not this file.

## `test_reachability_auditor.py`

Required files, all present:

- `data/vision_level39.json`
- `data/conveyor_calibration.json`
- `data/conveyor_visual_observations.json`

`reachability_auditor.audit(board, calibration, observations)` must yield:

- `results` length 8, and every result has a `scenarios` list (possibly empty only if the test's `all(...)` still holds; the eight-position test requires each item's `scenarios` to be truthy)
- every result with `observed_colour` `blue` has `candidate_board_colours` `["blue", "cyan"]` and exactly two scenarios
- `gameplay_verified`, `game_taps_enabled`, and `conveyor_identity_verified` all false
- `same_board_state_confirmed` false
- `planning_ready_positions` `0`
- every result `planning_eligible` false
- at least one result with `observed_ammo` `0`, and those results have `ammunition_available` false and `planning_eligible` false

Calibration needs `verified_by_user` true, `image_size`, and `shooters` entries with `id`, `segment`, and `center`. Observations need `observations[]` objects with `position_id`, `colour`, and `ammo`. Board geometry still has to place each calibrated shooter on a cell inside the board; that mapping comes from `conveyor_geometry` and is not satisfied by this document alone.

## What is still blocked

No genuine Level 39 screenshot, shooter crop, conveyor calibration, or visual
observation set is in the public repository. Until those captures are supplied
by someone who actually recorded them, the evidence tests above must remain
skipped. Device timing, tap safety, and solver optimality are not established
by the synthetic tests.
