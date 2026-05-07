"""Phase 2.0 — streaming variant of the Pipelex bridge activity.

Wraps :func:`pipelex.plugins.mistralai_workflows.bridge.run_pipe_via_bridge`
in a single Mistral Workflows ``Task`` so subscribers can observe the pipe
run through ``CustomTaskStarted`` / ``CustomTaskInProgress`` /
``CustomTaskCompleted`` / ``CustomTaskFailed`` events.

Phase 2.0 emits exactly two state transitions per call: ``started`` (on entry)
and ``completed`` (after the bridge returns). On exception, ``Task.__aexit__``
emits ``CustomTaskFailed`` automatically and the original exception
propagates. Per-step granularity (mapping Pipelex's ``report_delegate`` events
to ``Task.update_state`` calls) is Phase 2.1 and lives in this same module
when added.

Importing this module triggers the optional-dep guard: if
``mistralai-workflows`` is not installed, the import fails fast with a
``MistralWorkflowsNotInstalledError`` carrying install instructions. The
sibling ``activities`` module follows the same pattern.
"""

from datetime import timedelta

from pydantic import BaseModel, ConfigDict

from pipelex.plugins.mistralai_workflows.bridge import (
    PipelexPipeRunInput,
    PipelexPipeRunOutput,
    run_pipe_via_bridge,
)
from pipelex.plugins.mistralai_workflows.exceptions import MistralWorkflowsNotInstalledError

try:
    from mistralai.workflows import activity
    from mistralai.workflows.core.task import Task
except ImportError as exc:
    msg = (
        "The 'mistralai-workflows' optional dependency is required to use "
        "pipelex.plugins.mistralai_workflows.streaming. "
        "Install with: pip install 'pipelex[mistralai-workflows]'"
    )
    raise MistralWorkflowsNotInstalledError(msg) from exc


PIPELEX_PIPE_RUN_TASK_TYPE = "pipelex.pipe_run"


class PipelexPipeRunStreamingState(BaseModel):
    """Observable state surfaced through Mistral's Task API for a Pipelex pipe run.

    Phase 2.0 only writes ``started`` (on entry) and ``completed`` (after the
    bridge returns successfully). On failure, ``Task.__aexit__`` emits
    ``CustomTaskFailed`` with the exception message — no extra state write
    is needed and the original exception is preserved.
    """

    model_config = ConfigDict(extra="forbid")

    phase: str
    pipe_code: str
    execution_mode: str
    pipeline_run_id: str | None = None
    main_stuff_name: str | None = None


@activity(
    start_to_close_timeout=timedelta(minutes=10),
    retry_policy_max_attempts=3,
)
async def pipelex_run_pipe_streaming(input_payload: PipelexPipeRunInput) -> PipelexPipeRunOutput:
    """Streaming variant of ``pipelex_run_pipe``.

    Same semantics as :func:`pipelex_run_pipe` but wraps the bridge call in a
    single Mistral ``Task`` whose lifecycle (``started``, ``in_progress``,
    ``completed`` / ``failed``) is published to whichever events client the
    worker is configured with. For the silent path (no observability needed)
    use ``pipelex_run_pipe`` instead — the streaming variant adds a small
    constant overhead per activity for the lifecycle events.
    """
    initial_state = PipelexPipeRunStreamingState(
        phase="started",
        pipe_code=input_payload.pipe_code,
        execution_mode=input_payload.execution_mode,
        pipeline_run_id=input_payload.pipeline_run_id,
    )
    async with Task[PipelexPipeRunStreamingState](
        type=PIPELEX_PIPE_RUN_TASK_TYPE,
        state=initial_state,
    ) as streaming_task:
        output = await run_pipe_via_bridge(input_payload)
        await streaming_task.update_state(
            {
                "phase": "completed",
                "pipeline_run_id": output.pipeline_run_id,
                "main_stuff_name": output.main_stuff_name,
            }
        )
    return output
