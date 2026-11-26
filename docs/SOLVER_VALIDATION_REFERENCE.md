# Solver input-state validation boundary

The simulation engine expects a mutable rectangular board represented as
lists of rows. Every board cell is either a non-empty colour-label string or
`null`/Python `None` for an empty cell. Conveyor and storage fields are
lists of non-empty shooter IDs; shooter records must expose a valid shooter
contract, and occupied IDs must refer to known records.

`GameState.validate()` is the structural gate used before dry-run and
multi-batch simulation. It returns diagnostics for malformed container types,
non-list rows, empty/ragged boards, invalid board cells, malformed shooter
records and invalid occupancy references instead of raising incidental
`TypeError` exceptions while trying to validate them. The solver rejects a
state with validation errors before exploring candidates.

## Reproducible test cases

Run the standard unit suite to exercise the structural regression cases:

- `test_game_state_validation.py`: malformed top-level boards, invalid row
  containers, empty/ragged grids, invalid cell types, malformed shooter
  records, unhashable occupancy entries and a valid control state.
- `test_solver.py`: a matching colour is removed, an intervening different
  colour blocks the ray without consuming ammunition, successive shots expose
  the next matching cell, and unknown/zero ammunition and invalid directions
  are rejected.
- `test_execution_engine.py`: dry-run state immutability, bonded-group
  integrity, ammunition constraints, candidate limits and simulation-only
  execution restrictions.

These tests are hand-checkable examples of the repository's declared
simulation contract. They are **not** independent evidence that the actual
Slime Loop game follows every modeled rule, that the planner is globally
optimal, or that a recommendation will succeed on a real device. Game-rule
coverage still needs confirmation against genuine captures and independently
reviewed gameplay evidence. Live game actions remain disabled.


## Table-driven reference corpus

`data/solver_reference_cases.json` contains eleven hand-checkable simulator
cases. The corpus includes upward, downward, leftward and rightward rays,
passing through empty cells, blocking at the first different colour, an empty
ray, zero ammunition, unknown ammunition, successive removal of newly exposed
matching pixels, and a shooter starting outside the board boundary. `test_solver_reference_cases.py` compares every
shot result, reason, position, remaining-ammunition value and resulting board
against the fixture.

The direct `simulate_shot()` API also has negative-input regressions for
malformed ammunition types, non-string directions, non-integer coordinates,
unknown shooter colours and malformed board structures. These checks ensure
the low-level callable fails closed even when callers bypass the higher-level
`run_dry_simulation()` GameState gate.

The fixture is a transparent oracle for the code's current ray-simulation
contract. It is not a record of externally observed game outcomes and cannot
replace independent confirmation that the live game uses the same rules.


## Reference fixture schema

The table-driven test validates the fixture itself before using it as an oracle.
It requires exact top-level, case, shooter and expected-step field sets; exact
integer/boolean types; known cardinal directions; rectangular board snapshots;
and correctly shaped expected result boards. This prevents Python's
`True == 1` numeric equality or missing fields from silently weakening the
test oracle. It validates fixture structure only, not the truth of the modeled
game mechanics.

## Dry-run outcome reference corpus

`data/solver_outcome_reference_cases.json` contains five table-driven
planning-boundary examples. `test_solver_outcome_reference_cases.py`
validates the fixture schema, requires rectangular boards for valid cases,
and compares the dry-run report to each expected outcome:

- A matching candidate can empty the modeled board (`remaining_pixels == 0`).
  This is a simulator result, not proof of a live-game win condition.
- No accessible group returns `NO_LEGAL_BATCH` without examining candidates.
- A legal shot blocked by a different colour can still return `SIMULATED`
  with zero pixels removed and the board unsolved. `SIMULATED` means the
  candidate was evaluated; it does not mean the puzzle was solved.
- Explicitly unverified screenshot provenance returns
  `BLOCKED_UNVERIFIED_CAPTURE_PROVENANCE` without producing a candidate.
- A ragged board raises the controlled `GameState validation failed` error
  before candidate search begins.

These examples pin the current software contract for no-legal-move, unsolved,
provenance-blocked and invalid states. They are synthetic code-level cases,
not independently observed game outcomes or proof that the modeled rules
match live Slime Loop gameplay. Every returned report continues to state that
evidence is unverified and live execution/gameplay actions are disabled.

