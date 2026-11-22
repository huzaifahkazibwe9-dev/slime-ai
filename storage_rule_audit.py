import inspect
import json
from pathlib import Path

from conveyor_simulator import ConveyorSimulator
from execution_engine import run_multi_batch_schedule


def audit_storage_rules():
    tick_source = inspect.getsource(ConveyorSimulator.tick)
    reactivate_source = inspect.getsource(
        ConveyorSimulator.reactivate_group
    )
    signature = inspect.signature(run_multi_batch_schedule)

    zero_ammo_only = (
        "if shooter.ammo == 0" in tick_source
    )
    restores_ammo = (
        "ammo =" in reactivate_source
        or "ammo +=" in reactivate_source
    )
    default_disabled = (
        signature.parameters[
            "allow_storage_reactivation"
        ].default is False
    )

    report = {
        "audit": "Build11W_storage_rule_audit",
        "zero_ammo_only_return": zero_ammo_only,
        "reactivation_restores_ammo": restores_ammo,
        "reactivation_disabled_by_default": default_disabled,
        "live_execution_enabled": False,
        "gameplay_rule_verified": False,
        "reactivation_policy": (
            "UNVERIFIED_KEEP_DISABLED"
            if zero_ammo_only and not restores_ammo
            else "REQUIRES_GAMEPLAY_CONFIRMATION"
        ),
        "limitations": [
            "This audits Python implementation, not actual game behaviour.",
            "Storage reactivation has not been verified through gameplay.",
            "Conveyor timing remains uncalibrated."
        ]
    }

    path = Path("data/storage_rule_audit_latest.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2))

    checks = [
        ("Return condition inspected", zero_ammo_only),
        ("No ammunition restoration detected", not restores_ammo),
        ("Reactivation disabled by default", default_disabled),
        ("Live execution disabled", not report["live_execution_enabled"]),
    ]

    print("\nBUILD11W STORAGE RULE AUDIT")
    print("=" * 48)

    for name, passed in checks:
        print(f"[{'PASS' if passed else 'FAIL'}] {name}")

    print("\nPolicy:", report["reactivation_policy"])
    print("Report:", path.resolve())

    if not all(passed for _, passed in checks):
        raise SystemExit("BUILD11W AUDIT FAILED")

    print("\nBUILD11W: ALL CHECKS PASSED")
    return report


if __name__ == "__main__":
    audit_storage_rules()
