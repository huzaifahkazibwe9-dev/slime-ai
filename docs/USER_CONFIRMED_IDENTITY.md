# Human-confirmed shooter identity observations

The candidate matcher no longer assumes that a fixed shooter ID belongs to a
fixed conveyor position. It consumes a user-confirmed identity report generated
from `shooter_identity_observations.json`.

The source observation file is local and ignored by Git because it contains
human-entered evidence about a particular game capture. Do not commit private
screenshots or observation files.

## Required JSON shape

The build pipeline first runs `prepare_identity_observations.py`. If the
observation file is absent, the generator creates a blank, unverified template
from the exact current board, conveyor observations, calibration and shooter
detection files. It never overwrites an existing user file. The generator
records those four source hashes in the template; the identity auditor checks
them against the current files before accepting any records.

Create or complete `data/shooter_identity_observations.json` with this
structure. The
identifiers and positions below are illustrative placeholders, not verified
Level 39 values:

```json
{
  "board_snapshot_id": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "capture_session_id": "level39-session-01",
  "captured_at": "2026-11-25T08:00:00+00:00",
  "timestamp_identified": true,
  "verified_by_user": true,
  "current_frame_id": "current-frame",
  "observations": [
    {
      "frame_id": "current-frame",
      "position_id": "bottom_1",
      "shooter_id": "top_1",
      "verified": true
    },
    {
      "frame_id": "current-frame",
      "position_id": "bottom_2",
      "shooter_id": "top_2",
      "verified": true
    }
  ]
}
```

The example contains only two records to illustrate the structure. A valid
report requires the frame named by `current_frame_id` to map **every currently
detected visible shooter** from `data/shooter_detection.json` to one distinct
calibrated conveyor position. A calibrated position may be empty in the current
frame; do not invent an occupant for it.

Across the current and historical frames, the observations must cover every
position listed in `data/conveyor_calibration.json`. Within each frame, no two
shooters may occupy the same position, and one shooter may not occupy multiple
positions at once.

## Field requirements

| Field | Requirement |
|---|---|
| `board_snapshot_id` | Exact snapshot ID from the current board observation JSON |
| `capture_session_id` | Exact session ID used by the current board and shooter capture |
| `captured_at` | Real capture time in ISO-8601 format, including UTC offset |
| `timestamp_identified` | `true` only when the capture time is genuinely known |
| `verified_by_user` | `true` only after a person has checked the position-to-shooter mapping |
| `current_frame_id` | Frame ID whose records describe the current conveyor arrangement |
| `frame_id` | Groups records from one observed arrangement |
| `source_file_sha256` | Exact board, conveyor-observation, calibration and shooter-detection hashes recorded by the template generator |
| `position_id` | Exact ID from the conveyor calibration file |
| `shooter_id` | Exact ID from the shooter detection file |
| `verified` | `true` only when this individual mapping was visually checked |

Historical frame records may be included to track the same physical shooter
across different conveyor positions. Each frame must not assign two shooters to
one position or one shooter to multiple positions. The frame named by
`current_frame_id` must include every currently detected shooter exactly once,
and the combined history must cover all calibrated conveyor positions. The
audit reports `positions_checked` as the number of current detected shooters
mapped in that frame.

## Evidence and safety rules

- Do not copy predicted IDs into the file and then mark them verified. Confirm
  each mapping independently from the actual capture.
- The board, conveyor observation and identity-observation timestamps must be
  timezone-aware and aligned within the auditor's 120-second limit.
- The conveyor observations must explicitly confirm that they describe the
  same board state as the board screenshot.
- The template generator fingerprints the exact bytes of the board, visual
  observations, conveyor calibration and shooter detection files. The auditor
  compares those template hashes with the current inputs before accepting
  records, then fingerprints the identity observation file itself.
- A change to the board, visual observations, calibration or shooter detection
  after template creation requires a new template or re-confirmation.
- The matcher checks those hashes again before deriving candidate tracks.
- A valid identity report confirms only the human-checked physical
  shooter-to-position relationship for that capture. It does **not** verify
  shooter colour classification, ammunition OCR, firing behaviour, tile
  removal semantics, or gameplay success.
- Missing or invalid identity evidence blocks candidate matching. It does not
  enable taps, purchases, or other live game actions.

The normal build pipeline runs the identity auditor and candidate matcher
before reachability and planning. The reports are written to
`data/identity_audit_report.json` and
`data/conveyor_identity_candidates.json`. They remain local generated
evidence, not committed calibration truth.
