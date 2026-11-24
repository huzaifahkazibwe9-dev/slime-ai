# Independent source-pixel audit

The source-pixel audit independently checks whether every saved board RGB sample
can be reproduced from the original screenshot bytes.

Run it with:

```bash
python source_pixel_audit.py data/board_observation_latest.json --source-image screenshots/level39.jpg
```

The audit verifies the screenshot SHA-256 and dimensions, declared grid and
calibration bounds, sample-centre coordinates, sampling-method identifier,
and every stored 3x3 median RGB value. Pixel medians are recomputed with Pillow
pixel reads and Python's `statistics.median`, separately from the NumPy-based
extraction implementation. It also checks whether saved board labels and colour
counts agree with the source-derived RGB samples and the current shared
classifier.

A mismatch is reported per board coordinate. Malformed or incomplete
provenance and geometry are rejected rather than silently accepted.

## What this does not prove

- Calibration bounds align with the visible game tiles.
- The screenshot depicts the intended or current game state.
- The shared colour classifier matches the game's true colour semantics.
- Human labels are correct or representative.
- Gameplay, solver recommendations, or live interactions are verified.

The report deliberately keeps `calibration_alignment_verified`,
`label_truth_independently_verified`, and `gameplay_verified` false, and
`game_taps_enabled` false. A successful pixel audit proves byte-level
reproducibility of the recorded samples only.
