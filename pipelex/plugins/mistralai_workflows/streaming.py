"""Phase 2.1 — streaming variant of the Pipelex bridge activity.

Wraps a Pipelex pipe run in a single Mistral Workflows ``Task`` so subscribers
can observe progress through ``CustomTaskStarted`` / ``CustomTaskInProgress``
/ ``CustomTaskCompleted`` / ``CustomTaskFailed`` events.

Phase 2.0 emitted exactly two state transitions per call (``started`` /
``completed``). Phase 2.1 adds **per-step granularity** for ``DIRECT`` mode:
the activity opens a per-call ``GraphTracerManager`` tracer with a
queue-backed event log injected, and an asyncio forwarder drains the queue
into ``Task.update_state`` so each Pipelex pipe boundary produces a
``CustomTaskInProgress`` event. ``TEMPORAL_BLOCKING`` and
``TEMPORAL_FIRE_AND_FORGET`` keep Phase 2.0 behavior — per-step streaming
across the Temporal worker boundary is a future phase.

Importing this module triggers the optional-dep guard: if
``mistralai-workflows`` is not installed, the import fails fast with a
``MistralWorkflowsNotInstalledError`` carrying install instructions. The
sibling ``activities`` module follows the same pattern.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Any

import shortuuid
from pydantic import BaseModel, ConfigDict

from pipelex.graph.graph_tracer_manager import GraphTracerManager
from pipelex.plugins.mistralai_workflows.bridge import (
    PipelexPipeRunInput,
    PipelexPipeRunOutput,
    run_pipe_via_bridge,
)
from pipelex.plugins.mistralai_workflows.exceptions import MistralWorkflowsNotInstalledError
from pipelex.plugins.mistralai_workflows.execution_mode import PipelexExecutionMode
from pipelex.plugins.mistralai_workflows.streaming_event_forwarder import (
    SHUTDOWN_SENTINEL,
    QueueEventLog,
    build_streaming_data_inclusion,
    forward_events_to_task,
    get_drain_timeout_seconds,
    get_queue_max_size,
)

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

    Phase 2.0 fields (always present):

    - ``phase``: one of ``"started"`` / ``"in_progress"`` / ``"completed"``.
      ``"failed"`` is not written explicitly — ``Task.__aexit__`` emits
      ``CustomTaskFailed`` on exception and the original exception
      propagates.
    - ``pipe_code`` / ``execution_mode`` / ``pipeline_run_id`` /
      ``main_stuff_name``: identifiers, set on ``started`` and refined on
      ``completed``.

    Phase 2.1 fields (only populated for DIRECT mode runs that go through
    ``pipelex_run_pipe_streaming``; remain at defaults for TEMPORAL modes):

    - ``current_step_pipe_code`` / ``current_step_node_id``: identify the
      pipe boundary that just fired.
    - ``last_event_kind``: ``"pipe_start"`` / ``"pipe_end_success"`` /
      ``"pipe_end_error"`` — lets subscribers route on event type.
    - ``started_steps`` / ``completed_steps``: cumulative counters,
      monotonic, 1-indexed.
    - ``last_output_stuff_name``: the IOSpec name of the most recent
      successful step's output, or ``None`` if the step had no output spec.
    """

    model_config = ConfigDict(extra="forbid")

    phase: str
    pipe_code: str
    execution_mode: str
    pipeline_run_id: str | None = None
    main_stuff_name: str | None = None

    current_step_pipe_code: str | None = None
    current_step_node_id: str | None = None
    last_event_kind: str | None = None
    started_steps: int = 0
    completed_steps: int = 0
    last_output_stuff_name: str | None = None


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

    For ``DIRECT`` execution mode, opens a per-call ``GraphTracerManager``
    tracer with an in-process queue-backed event log; spawns a forwarder
    coroutine that translates each ``PipeStartEvent`` /
    ``PipeEndSuccessEvent`` / ``PipeEndErrorEvent`` into a
    ``Task.update_state`` call so subscribers see one
    ``CustomTaskInProgress`` per pipe boundary. ``TEMPORAL_*`` modes keep
    the Phase 2.0 single-pair behavior.
    """
    pipeline_run_id = input_payload.pipeline_run_id or shortuuid.uuid()
    if input_payload.pipeline_run_id is None:
        input_payload = input_payload.model_copy(update={"pipeline_run_id": pipeline_run_id})

    initial_state = PipelexPipeRunStreamingState(
        phase="started",
        pipe_code=input_payload.pipe_code,
        execution_mode=input_payload.execution_mode,
        pipeline_run_id=pipeline_run_id,
    )

    if input_payload.execution_mode is PipelexExecutionMode.DIRECT:
        return await _run_streaming_with_per_step_events(
            input_payload=input_payload,
            pipeline_run_id=pipeline_run_id,
            initial_state=initial_state,
        )

    return await _run_streaming_without_per_step_events(
        input_payload=input_payload,
        initial_state=initial_state,
    )


async def _run_streaming_with_per_step_events(
    input_payload: PipelexPipeRunInput,
    pipeline_run_id: str,
    initial_state: PipelexPipeRunStreamingState,
) -> PipelexPipeRunOutput:
    """DIRECT-mode streaming path — opens a tracer + forwarder for per-step events."""
    event_queue: asyncio.Queue[Any] = asyncio.Queue(maxsize=get_queue_max_size())
    queue_event_log = QueueEventLog(loop=asyncio.get_running_loop(), queue=event_queue)
    tracer_manager = GraphTracerManager.get_or_create_instance()
    graph_context = tracer_manager.open_tracer(
        graph_id=pipeline_run_id,
        data_inclusion=build_streaming_data_inclusion(),
        pipeline_ref_domain=None,
        pipeline_ref_main_pipe=None,
        event_log=queue_event_log,
        workflow_id="direct",
        pipeline_run_id=pipeline_run_id,
    )

    try:
        async with Task[PipelexPipeRunStreamingState](
            type=PIPELEX_PIPE_RUN_TASK_TYPE,
            state=initial_state,
        ) as streaming_task:
            forwarder_task = asyncio.create_task(
                forward_events_to_task(
                    event_queue=event_queue,
                    update_state=streaming_task.update_state,
                ),
                name=f"pipelex-streaming-forwarder-{pipeline_run_id}",
            )
            output: PipelexPipeRunOutput | None = None
            try:
                output = await run_pipe_via_bridge(input_payload, graph_context=graph_context)
            finally:
                # Drain ALL pending per-step events BEFORE writing the final
                # "completed" state. If we wrote phase="completed" first, the
                # forwarder's still-pending pipe_end_success patches would race
                # the snapshot and the captured CustomTaskCompleted event would
                # read phase="in_progress".
                event_queue.put_nowait(SHUTDOWN_SENTINEL)
                try:
                    await asyncio.wait_for(forwarder_task, timeout=get_drain_timeout_seconds())
                except TimeoutError:
                    forwarder_task.cancel()
            # Bridge either returned (output is non-None) or raised inside the
            # try block above and we never reach this line.
            assert output is not None
            await streaming_task.update_state(
                {
                    "phase": "completed",
                    "pipeline_run_id": output.pipeline_run_id,
                    "main_stuff_name": output.main_stuff_name,
                }
            )
        return output
    finally:
        tracer_manager.close_tracer(pipeline_run_id)


async def _run_streaming_without_per_step_events(
    input_payload: PipelexPipeRunInput,
    initial_state: PipelexPipeRunStreamingState,
) -> PipelexPipeRunOutput:
    """TEMPORAL-mode streaming path — Phase 2.0 single-pair semantics, no tracer."""
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
