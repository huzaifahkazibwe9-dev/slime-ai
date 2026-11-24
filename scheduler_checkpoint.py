"""Versioned scheduler checkpoints for safe batch-boundary recovery.

A checkpoint is captured only after a batch has completed successfully and
before the next batch begins. It is not a resumable iterator: callers must
supply the remaining, not-yet-consumed batches after restoration.
"""
import copy
import json

from simulator_snapshot import snapshot_simulator, restore_simulator

SCHEDULER_CHECKPOINT_SCHEMA_VERSION = 1


def _json_copy(value):
    try:
        encoded = json.dumps(value, allow_nan=False)
        return json.loads(encoded)
    except (TypeError, ValueError) as exc:
        raise ValueError("checkpoint data must be JSON-compatible") from exc


def create_scheduler_checkpoint(
    simulator,
    next_batch_index,
    completed_batch_reports,
    groups_scheduled,
):
    """Create a detached checkpoint at a successful batch boundary."""
    if type(next_batch_index) is not int or next_batch_index < 0:
        raise ValueError("next_batch_index must be a non-negative integer")
    if not isinstance(completed_batch_reports, list):
        raise ValueError("completed_batch_reports must be a list")
    if next_batch_index != len(completed_batch_reports):
        raise ValueError("next_batch_index must equal completed report count")
    reports = _json_copy(completed_batch_reports)
    if any(
        not isinstance(report, dict) or report.get("valid") is not True
        for report in reports
    ):
        raise ValueError("only successfully completed batch reports can be checkpointed")
    if not isinstance(groups_scheduled, list) or any(
        not isinstance(group, str) or not group.strip()
        for group in groups_scheduled
    ):
        raise ValueError("groups_scheduled must be a list of non-empty strings")
    if len(groups_scheduled) != len(set(groups_scheduled)):
        raise ValueError("groups_scheduled must not contain duplicates")

    checkpoint = {
        "schema_version": SCHEDULER_CHECKPOINT_SCHEMA_VERSION,
        "simulation_only": True,
        "next_batch_index": next_batch_index,
        "completed_batch_reports": reports,
        "groups_scheduled": list(groups_scheduled),
        "simulator": snapshot_simulator(simulator),
        "live_execution_allowed": False,
        "gameplay_actions_performed": False,
    }
    return _json_copy(checkpoint)


def restore_scheduler_checkpoint(checkpoint):
    """Validate and restore a checkpoint; return simulator and scheduler state."""
    data = _json_copy(checkpoint)
    if not isinstance(data, dict):
        raise ValueError("checkpoint must be an object")
    if data.get("schema_version") != SCHEDULER_CHECKPOINT_SCHEMA_VERSION:
        raise ValueError("unsupported scheduler checkpoint schema version")
    if data.get("simulation_only") is not True:
        raise ValueError("checkpoint must be explicitly simulation-only")
    if data.get("live_execution_allowed") is not False:
        raise ValueError("checkpoint cannot enable live execution")
    if data.get("gameplay_actions_performed") is not False:
        raise ValueError("checkpoint cannot claim gameplay actions")

    next_index = data.get("next_batch_index")
    reports = data.get("completed_batch_reports")
    groups = data.get("groups_scheduled")
    if type(next_index) is not int or next_index < 0:
        raise ValueError("next_batch_index must be a non-negative integer")
    if not isinstance(reports, list) or next_index != len(reports):
        raise ValueError("checkpoint report count does not match next batch index")
    if any(
        not isinstance(report, dict) or report.get("valid") is not True
        for report in reports
    ):
        raise ValueError("checkpoint contains an incomplete batch report")
    if not isinstance(groups, list) or any(
        not isinstance(group, str) or not group.strip()
        for group in groups
    ):
        raise ValueError("groups_scheduled must be a list of non-empty strings")
    if len(groups) != len(set(groups)):
        raise ValueError("groups_scheduled must not contain duplicates")

    simulator = restore_simulator(data.get("simulator"))
    return {
        "simulator": simulator,
        "next_batch_index": next_index,
        "completed_batch_reports": copy.deepcopy(reports),
        "groups_scheduled": list(groups),
        "simulation_only": True,
        "live_execution_allowed": False,
        "gameplay_actions_performed": False,
    }
