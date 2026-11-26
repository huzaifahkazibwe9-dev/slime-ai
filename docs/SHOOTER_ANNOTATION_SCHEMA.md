# Shooter Annotation Schema (Human Review Only)

**Purpose:** Define the required format for human-reviewed ground-truth labels of shooter identity, colour, ammunition, and bonded groups.

This schema exists so that future accuracy measurements can be performed against independently verified human labels.  
**No AI, script, or offline process may invent or generate these labels.**  
Labels must come from a human who has examined the original screenshot.

## File format

A single JSON object per capture:

```json
{
  "annotation_version": "1.0",
  "capture_session_id": "session-2026-11-26-001",
  "board_snapshot_id": "sha256:abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789",
  "annotated_at": "2026-11-26T12:00:00+00:00",
  "annotator": "human-reviewer-id",
  "human_confirmed": true,
  "notes": "optional free-text observation notes",
  "shooters": [
    {
      "id": "s1",
      "color": "red",
      "ammo": 20,
      "slot_index": 0,
      "bonded_ids": ["s2"]
    }
  ]
}
```

## Required fields

| Field | Type | Constraints |
|-------|------|-------------|
| annotation_version | string | must be `"1.0"` |
| capture_session_id | string | non-empty, matches existing session rules |
| board_snapshot_id | string | `sha256:` + 64 hex chars |
| annotated_at | string | aware ISO-8601 timestamp |
| annotator | string | non-empty |
| human_confirmed | boolean | **must be exactly `true`** |
| shooters | array | may be empty only if the human explicitly confirms no shooters were visible |

Each shooter object:

- `id` (string, non-empty)
- `color` (string, non-empty)
- `ammo` (integer ≥ 0)
- `slot_index` (integer 0–11, optional but recommended)
- `bonded_ids` (array of strings, optional)

## Validation rules (enforced by `annotation_validator.py`)

- `human_confirmed` must be the boolean `true`. Any other value (including missing, `false`, or a string) causes rejection.
- All required top-level fields must be present and correctly typed.
- Snapshot ID must match the expected SHA-256 format.
- No field may be auto-filled by code; the validator only accepts or rejects.

## Status

Schema and validator are offline-verifiable.  
Actual annotation files remain **blocked** until a human supplies them.  
Do not place synthetic or AI-generated labels in `evidence/final/`.
