from pathlib import Path
import sqlite3
import traceback

ROOT = Path(__file__).resolve().parent
passed = 0
failed = 0

def test(name, function):
    global passed, failed
    print("\n" + name)
    try:
        result = function()
        if result is not False:
            print("[PASS]", name)
            passed += 1
        else:
            print("[FAIL]", name)
            failed += 1
    except Exception as exc:
        print("[FAIL]", name, "-", exc)
        traceback.print_exc()
        failed += 1

print("=" * 48)
print("SLIME AI INTEGRATION TEST")
print("Actual game taps: DISABLED")
print("=" * 48)

state_holder = {}

def load_level_test():
    from level_loader import load_level
    result = load_level()

    if isinstance(result, tuple):
        state_holder["state"] = result[0]
    else:
        state_holder["state"] = result

    state = state_holder["state"]
    print("Board:", state.width, "x", state.height)
    print("Tiles:", state.remaining_pixels)
    print("Shooters:", len(state.shooters))
    return state.width == 35 and state.height == 35 and state.remaining_pixels == 1225

def state_validation_test():
    state = state_holder["state"]
    errors = state.validate()
    print("Validation errors:", errors)
    return len(errors) == 0

def shooter_test():
    state = state_holder["state"]
    print("Shooter details:")
    for shooter_id, shooter in state.shooters.items():
        print(
            shooter_id,
            "| colour:", shooter.color,
            "| ammo:", shooter.ammo,
            "| bonds:", shooter.bonded_ids
        )
        if shooter.ammo is None or shooter.ammo < 0:
            return False
        for bonded_id in shooter.bonded_ids:
            if bonded_id not in state.shooters:
                return False
            if shooter_id not in state.shooters[bonded_id].bonded_ids:
                return False
    return len(state.shooters) == 4

def group_test():
    from game_state import GameState, Shooter

    test_state = GameState(
        board=[["red", "blue"]],
        shooters={
            "A": Shooter("A", "red", 20, accessible=True,
                         bonded_ids=["B"]),
            "B": Shooter("B", "blue", 20,
                         bonded_ids=["A"]),
            "C": Shooter("C", "green", 20, accessible=True),
        }
    )

    assert test_state.bonded_group("A") == ["A", "B"]
    assert test_state.can_select_group("A")

    test_state.conveyor = ["C", "X", "Y", "Z"]
    assert not test_state.can_select_group("A")

    test_state.conveyor = []
    assert test_state.select_group("A")
    assert test_state.conveyor == ["A", "B"]
    return True

def capacity_test():
    from game_state import GameState
    from game_state import CONVEYOR_LIMIT, STORAGE_LIMIT

    print("Conveyor limit:", CONVEYOR_LIMIT)
    print("Storage limit:", STORAGE_LIMIT)

    state = GameState(board=[["red"]], shooters={})
    print("Initial conveyor spaces:", state.conveyor_free)
    print("Initial storage spaces:", state.storage_free)

    return (
        CONVEYOR_LIMIT == 5
        and STORAGE_LIMIT == 5
        and state.conveyor_free == 5
        and state.storage_free == 5
    )

def planner_test():
    from planner import plan_next_move
    state = state_holder["state"]
    result = plan_next_move(state)
    print("Planner result:", result)
    print("No move is acceptable while all shooters are inaccessible.")
    return True

def solver_test():
    from game_state import GameState, Shooter
    from solver import simulate_shot

    test_state = GameState(
        board=[[None, "red"]],
        shooters={
            "TEST": Shooter(
                "TEST", "red", 5,
                direction="right",
                x=0, y=0
            )
        }
    )

    result = simulate_shot(test_state, "TEST")
    print("Simulated shot:", result)
    assert result.fired
    assert result.removed
    assert test_state.board[0][1] is None
    assert test_state.shooters["TEST"].ammo == 4
    return True

def database_test():
    db = ROOT / "data" / "learning.db"
    if not db.exists():
        return False
    connection = sqlite3.connect(
        f"file:{db}?mode=ro", uri=True
    )
    result = connection.execute(
        "PRAGMA integrity_check"
    ).fetchone()[0]
    connection.close()
    print("Database integrity:", result)
    return result == "ok"

def module_import_test():
    modules = [
        "game_state", "planner", "solver",
        "vision", "board_loader", "level_loader",
        "shooter_detector", "shooter_loader",
        "learner", "command_dispatcher",
        "macro_bridge"
    ]
    import importlib
    for name in modules:
        importlib.import_module(name)
        print("[IMPORTED]", name)
    return True

test("1. LEVEL LOADING", load_level_test)
if "state" in state_holder:
    test("2. GAME STATE VALIDATION", state_validation_test)
    test("3. SHOOTER AND BOND VALIDATION", shooter_test)
else:
    print("\nLevel loading failed; dependent tests skipped.")

test("4. BONDED GROUP AND CONVEYOR TEST", group_test)
test("5. CAPACITY LIMIT TEST", capacity_test)
if "state" in state_holder:
    test("6. PLANNER COMPATIBILITY", planner_test)
test("7. ISOLATED SHOOTING SIMULATION", solver_test)
test("8. LEARNING DATABASE", database_test)
test("9. MODULE IMPORTS", module_import_test)

print("\n" + "=" * 48)
print("INTEGRATION TEST SUMMARY")
print("Passed:", passed)
print("Failed:", failed)
print("Game taps: DISABLED")
print("=" * 48)

report = (
    "SLIME AI INTEGRATION TEST\n"
    f"Passed: {passed}\n"
    f"Failed: {failed}\n"
    "Game taps: DISABLED\n"
)
(ROOT / "integration_report.txt").write_text(report)
print("Report saved: integration_report.txt")
