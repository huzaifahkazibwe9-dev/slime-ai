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
- `test_bonded_group_reference_cases.py`: exact-schema, table-driven checks for
  two- and three-member bonded groups, sequential board mutation, shared-target
  depletion, atomic selection, per-member ammunition and source immutability.

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



## Dry-run candidate-budget validation

`run_dry_simulation()` validates `max_candidates` after the GameState structural check and before the screenshot-provenance early return. The value must be an exact positive integer; booleans, floats, zero, negative values, `None` and strings are rejected consistently even when unverified provenance would otherwise block candidate planning. A valid budget still returns the provenance-blocked report without examining candidates. This is an API input-contract guarantee, not a change to candidate search, screenshot trust or game-rule assumptions.

## Deterministic bounded candidate ordering

Before enumerating dry-run candidate prefixes, `run_dry_simulation()` sorts eligible accessible groups by their canonical sorted shooter-ID tuple. This makes the traversal order independent of the insertion order of the shooter's mapping in an otherwise equivalent `GameState`. The table-driven regression test `test_bounded_search_uses_canonical_group_order` builds equivalent states with reversed shooter insertion order and confirms that a one-candidate budget selects the same first group in both states.

This guarantee concerns repeatable traversal under a fixed state and candidate budget. It does not expand the budget, eliminate truncation, change scoring, validate unobserved game mechanics or prove global solver optimality. Live gameplay actions remain disabled.


## Bonded-group reference corpus

`data/bonded_group_reference_cases.json` contains three synthetic, hand-checkable outcomes for `simulate_bonded_group()`. The paired cases cover members firing sequentially against the same evolving board, including a shared target that the first member removes before the second member is simulated. A third case covers atomic selection and ordered simulation of a complete three-member group. `test_bonded_group_reference_cases.py` validates exact fixture field sets and primitive types, then compares group membership, conveyor selection, per-member shot steps and ammunition, total pixel counts, final board, source-state immutability and the simulation-only safety flags.

These fixtures pin the current software contract; they are not captured gameplay examples and do not prove that the live game uses the same bonded-group rules, firing order or board mechanics. Independent game evidence and device validation remain outstanding. Live gameplay actions remain disabled.

## Invalid bonded-group reference corpus

`data/bonded_group_invalid_reference_cases.json` contains six negative states: a non-reciprocal/asymmetric pair, a dangling shooter reference, a non-list bond container, a non-string bond member, conflicting explicit group IDs and a four-member component beyond the supported maximum. `test_bonded_group_invalid_reference_cases.py` checks the exact fixture schema and expected validation diagnostics, then verifies that component lookup/identity, selectability, attempted selection and the bonded-group simulator all fail closed without mutating the source state.

The asymmetric case intentionally distinguishes graph discovery from permission to select: the connected component can be discovered, but a missing reciprocal edge causes validation failure and selection is refused. The fixtures are synthetic input-contract examples, not evidence about live game grouping. The maximum group size and reciprocal-link requirements are the current code contract, not claims about externally confirmed game rules.

## Bonded-group selectability boundary corpus

`data/bonded_group_selectability_cases.json` contains eight synthetic states
for `GameState.can_select_group()` and `select_group()`. The cases cover a
two-member group with one conveyor slot free, an exact-fit capacity boundary,
a group member already in conveyor or storage, duplicate occupancy IDs within
the conveyor and across conveyor/storage, duplicate bonded references, and a
self-referential bond. The exact-schema table-driven test compares validation
diagnostics, component membership and identity, selectability, selection
results, final occupancy and source-state immutability.

The direct selection helper now rejects malformed occupancy containers,
over-capacity occupancy, unknown or repeated occupied IDs, duplicate bonded
references and self-links. This closes a direct-call bypass where repeated
bond metadata could pass component traversal even though `Shooter.valid()`
and `GameState.validate()` reject it. These cases document the current
software contract only; they are synthetic and do not verify live-game
conveyor rules or timing. Gameplay actions remain disabled.

## Bonded-group storage transition boundaries

The low-level `GameState.can_return_from_storage()` and
`transfer_from_storage()` helpers now treat a bonded component as one
indivisible storage-to-conveyor transition. A transfer is allowed only when
every member is present in storage, the component links and group identity are
consistent, occupancy IDs are known and unique, container capacities are
valid, and the conveyor has room for the entire component. A successful
transfer moves all members in stable order and resets each member's
`rotation_progress`; rejected operations leave the state unchanged.

`test_game_state_storage_transitions.py` covers exact-fit and one-slot-short
conveyor capacity, partially stored groups, groups split across storage and
conveyor, duplicate storage occupancy, unbonded single-shooter compatibility
and malformed shooter identifiers. `test_conveyor_simulator.py` adds exact-fit
and insufficient storage return cases, plus no-mutation checks for
reactivation when conveyor space or recorded storage occupancy is insufficient.
`test_multi_batch_planner.py` covers whole-batch preflight when a returned
pair needs two conveyor slots but only one remains.

These are synthetic state-transition contract tests. They do not establish
live-game storage capacity, timing or reactivation rules; real device evidence
and independent mechanics review remain outstanding. All transitions remain
offline simulations; live actions stay disabled.

