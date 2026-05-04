from temporalio import workflow
from temporalio.exceptions import TemporalError


def is_in_temporal_workflow() -> bool:
    """Check if the current code is running inside a Temporal workflow.

    Uses workflow.info() which raises if not inside a workflow context.
    Used by `TemporalPipeRouter` and `TemporalPipeRun` to decide between top-level dispatch
    (`execute_workflow`) and child dispatch (`execute_child_workflow`).
    """
    try:
        workflow.info()
        return True
    except (TemporalError, RuntimeError):
        return False
