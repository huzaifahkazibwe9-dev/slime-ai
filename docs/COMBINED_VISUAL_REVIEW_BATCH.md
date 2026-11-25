# Multi-capture visual review batch evaluation

Use this only after at least two captures have each completed the single-capture workflow in [COMBINED_VISUAL_REVIEW.md](COMBINED_VISUAL_REVIEW.md). Every item is re-evaluated from its original screenshot, board observation, shooter detection, pixel audit, manifest, and completed human-label files. Precomputed reports alone are not accepted as batch input.

Create a batch manifest such as `data/visual_review_batch.json`:

```json
{
  "schema_version": 1,
  "bundles": [
    {
      "id": "level39-capture-1",
      "manifest": "capture-1/visual_review_bundle.json",
      "board_labels": "capture-1/colour_labels_template.json",
      "shooter_labels": "capture-1/shooter_labels_template.json",
      "board_observation": "capture-1/board_observation_latest.json",
      "shooter_detection": "capture-1/shooter_detection.json",
      "pixel_audit": "capture-1/source_pixel_audit_latest.json",
      "source_screenshot": "capture-1/original.png"
    },
    {
      "id": "level39-capture-2",
      "manifest": "capture-2/visual_review_bundle.json",
      "board_labels": "capture-2/colour_labels_template.json",
      "shooter_labels": "capture-2/shooter_labels_template.json",
      "board_observation": "capture-2/board_observation_latest.json",
      "shooter_detection": "capture-2/shooter_detection.json",
      "pixel_audit": "capture-2/source_pixel_audit_latest.json",
      "source_screenshot": "capture-2/original.png"
    }
  ]
}
```

All paths are relative to the batch-manifest directory. Absolute paths, parent-directory traversal, and symlinks resolving outside that directory are rejected. Bundle IDs must be unique. Each item must contain exactly the seven source/review paths shown above.

Run:

```bash
python evaluate_visual_review_batch.py data/visual_review_batch.json
```

The default report is written to `data/visual_review_batch_evaluation.json`; override it with `--output`.

The batch must contain at least two bundles. Duplicate source-screenshot SHA-256 values and duplicate capture-session IDs are rejected so the same capture cannot silently inflate sample support. If any member bundle fails source verification, the batch fails rather than producing a partial aggregate.

Board-colour results pool sample-level confusion counts, accuracy, and per-class precision/recall/F1. Shooter results pool visibility, slot-position alignment, colour, and ammunition metrics independently. Ambiguous shooter samples remain excluded from confirmed-sample metrics, while their count remains visible. The report retains per-capture identities, exact source-artifact hashes (board observation, shooter detection, pixel audit and original screenshot), and exact review-artifact hashes (manifest and both completed label files). It checks that the source screenshot digest agrees with the capture identity.

The batch evaluation report includes an `evaluation_sha256` digest calculated over its complete canonical JSON content (excluding that digest field). To verify a saved report programmatically, load the JSON object and call `verify_batch_report(report)` from `evaluate_visual_review_batch.py`. This detects accidental or uncoordinated content edits; it is an integrity checksum, not a digital signature or proof of who produced the report.

These are pooled agreement metrics against user-supplied human labels, not independent proof of label truth, calibration alignment, game colour semantics, ammunition truth, or gameplay success. A larger batch does not remove a systematic labelling bias. The batch evaluator does not enable game taps or purchases.
