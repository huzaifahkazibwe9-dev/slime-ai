# evidence/final/

This directory is reserved for **independently obtained** evidence required to complete offline and real-world validation of Slime AI.

## Currently present

- This README (process documentation only).

## Still required (do not invent or generate)

| Artifact | Description | Source | Status |
|----------|-------------|--------|--------|
| `device_screenshots/` | Real screenshots captured on the target Android device under Termux | Physical device | **Blocked** — requires human with the phone |
| `human_shooter_annotations/` | JSON files conforming to `docs/SHOOTER_ANNOTATION_SCHEMA.md` | Human reviewer examining original screenshots | **Blocked** — requires human labels |
| `level39_conveyor_fixtures/` | Private Level 39 / conveyor evidence currently skipped in public tests | Original capture session | **Blocked** — private data not shipped |
| `verified_solver_fixtures/` | Independently solved puzzles with known correct shot sequences | Human or independent solver | **Blocked** |

## Rules

- Never place AI-generated, synthetic, or placeholder labels that claim to be human-reviewed.
- Never enable gameplay taps or live automation to obtain evidence.
- All files that appear here must carry provenance (capture session, snapshot hash, annotator identity).
- The public repository intentionally omits private evidence; tests that need it remain skipped.

See `STATUS.md` and `docs/FINAL_COMPLETION_CHECKLIST.md` for the current honest status of each item.
