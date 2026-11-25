# Combined visual review evaluation

After preparing a review bundle with `prepare_visual_review.py` and completing both label templates, evaluate them together:

```bash
python evaluate_visual_review_bundle.py \
  data/visual_review_bundle.json \
  data/colour_labels_template.json \
  data/shooter_labels_template.json \
  --board-observation data/board_observation_latest.json \
  --shooter-detection data/shooter_detection.json \
  --pixel-audit data/source_pixel_audit_latest.json \
  --source-screenshot path/to/the/original-screenshot.png
```

The evaluator verifies manifest integrity, exact source-artifact hashes, capture session and timestamp, screenshot dimensions, and the board's source-pixel audit. It reconstructs both original blank templates and checks that the completed files differ only in their intended human annotation fields. Board RGB values and cell coordinates must still match the original board observation; shooter detector records must still match the exact detector JSON.

The evaluator then runs the board-colour and shooter-observation metrics and emits one combined report. It does not combine the two metrics into one accuracy number because they measure different tasks.

Review labels remain user-supplied evidence. Agreement metrics do not independently prove that human labels are correct, that calibration aligns to game tiles, or that shooter colour, ammunition, or slot mapping is correct. Gameplay remains unverified and live taps remain disabled.