# Multi-batch schedule checkpoints

The multi-batch planner supports bounded, simulation-only runs that can be
resumed from a JSON-compatible checkpoint.

## Create a checkpoint

Pass a finite list or tuple of batches and a positive `max_batches` value:

```python
from multi_batch_planner import simulate_batch_schedule

partial = simulate_batch_schedule(
    shooter_records,
    batches,
    config=config,
    allow_storage_reactivation=False,
    max_batches=3,
)
checkpoint = partial["checkpoint"]
```

A checkpoint is emitted only when the run stopped at the batch limit, the
processed batches are valid, the simulator has not failed, and unprocessed
batches remain. If the schedule finishes within the limit, `checkpoint` is
`None`. Invalid schedules and failed simulations do not produce resumable
checkpoints.

## Resume

Pass the original shooter records, the exact same batch sequence, the same
initial storage occupancy, the same simulator configuration, and the same
storage-reactivation setting, along with `resume_from=checkpoint`:

```python
continued = simulate_batch_schedule(
    shooter_records,
    batches,
    config=config,
    allow_storage_reactivation=False,
    resume_from=checkpoint,
)
```

The result reports `schedule_complete`, `next_batch_index`,
`batches_completed`, `batch_reports`, and `checkpoint`. A resumed run may
itself be bounded with `max_batches` to produce another checkpoint.

## Validation and constraints

- Checkpoint mode requires a finite `list` or `tuple` of batches. Ordinary
  non-checkpoint runs may still consume iterables/generators.
- The schedule fingerprint is SHA-256 over canonical JSON for the normalized
  shooter records, batches, initial storage occupancy, simulator capacities
  and tick configuration, and reactivation setting. It detects accidental
  input changes; it is not an authentication mechanism or a tamper-proof
  signature.
- Checkpoints have a schema version and contain the simulation-only flags,
  next batch index, completed batch reports, scheduled-group state, and a
  detached simulator snapshot.
- Resume validates the fingerprint, schema and safety flags, report ordering,
  scheduled-group bookkeeping, simulator configuration, shooter roster, and
  selected state for groups recorded as previously scheduled.
- Failed simulations cannot be resumed. A checkpoint is not a live-game save
  and cannot operate the game, tap controls, or purchase power-ups.
- The conveyor timing and storage-reactivation assumptions remain abstract
  simulation inputs; they have not been empirically calibrated to gameplay.

Treat checkpoints as untrusted input. Do not edit their contents manually.
