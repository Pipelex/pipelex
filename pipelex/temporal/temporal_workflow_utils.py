from temporalio import workflow
from temporalio.exceptions import TemporalError


def is_in_temporal_workflow() -> bool:
    """Check if the current code is running inside a Temporal workflow.

    Uses workflow.info() which raises if not inside a workflow context.
    Used by the hub to auto-switch between PipeRouterTop (outside) and PipeRouterChild (inside).
    """
    try:
        workflow.info()
        return True
    except (TemporalError, RuntimeError):
        return False
