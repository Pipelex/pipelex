"""Tier 1 — pre-decorated Mistral Workflows activity that runs a Pipelex pipe.

Importing this module triggers the optional-dep guard: if
``mistralai-workflows`` is not installed, the import fails fast with a
``MistralWorkflowsNotInstalledError`` carrying install instructions.
"""

from datetime import timedelta

from pipelex.plugins.mistralai_workflows.bridge import (
    PipelexPipeRunInput,
    PipelexPipeRunOutput,
    run_pipe_via_bridge,
)
from pipelex.plugins.mistralai_workflows.exceptions import MistralWorkflowsNotInstalledError

try:
    from mistralai.workflows import activity
except ImportError as exc:
    msg = (
        "The 'mistralai-workflows' optional dependency is required to use "
        "pipelex.plugins.mistralai_workflows.activities. "
        "Install with: pip install 'pipelex[mistralai-workflows]'"
    )
    raise MistralWorkflowsNotInstalledError(msg) from exc


@activity(
    start_to_close_timeout=timedelta(minutes=10),
    retry_policy_max_attempts=3,
)
async def pipelex_run_pipe(input_payload: PipelexPipeRunInput) -> PipelexPipeRunOutput:
    """Run a Pipelex pipe from inside a Mistral Workflows activity.

    Thin wrapper around ``run_pipe_via_bridge`` so users get a ready-to-register
    activity without having to write their own ``@activity`` decoration. For
    custom timeouts, retry policies, rate limits, or sticky-to-worker config,
    call ``run_pipe_via_bridge`` directly from your own ``@activity`` (Tier 2).
    """
    return await run_pipe_via_bridge(input_payload)
