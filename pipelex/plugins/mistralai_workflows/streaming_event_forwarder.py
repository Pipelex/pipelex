"""Per-step event forwarding for the streaming activity (Phase 2.1).

Bridges Pipelex's trace event channel into Mistral's ``Task.update_state``.
``streaming.py`` opens a per-call ``GraphTracerManager`` tracer with a
``QueueEventLog`` injected as the event log, then spawns
``forward_events_to_task`` to drain the queue and translate trace events
into ``Task.update_state(...)`` calls.

This module is framework-agnostic: it does NOT import ``mistralai.workflows``.
The forwarder takes the bound ``update_state`` coroutine as a callable so the
``Task`` type can stay isolated to ``streaming.py``.
"""

from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final, Literal

from typing_extensions import override

from pipelex import log
from pipelex.graph.graph_config import DataInclusionConfig
from pipelex.tracing.event_log_protocol import EventLogProtocol
from pipelex.tracing.trace_events import (
    BatchAggregateEvent,
    BatchItemEvent,
    ControllerOutputEvent,
    EdgeEvent,
    ExecutionDataEvent,
    ParallelCombineEvent,
    PipeEndErrorEvent,
    PipeEndSuccessEvent,
    PipeStartEvent,
    TraceEvent,
    UsageReportEvent,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

_QUEUE_MAX_SIZE: Final[int] = 256
_FORWARDER_DRAIN_TIMEOUT_SECONDS: Final[float] = 5.0


class _ShutdownSentinel:
    """Module-private sentinel type pushed onto the queue to stop the forwarder."""


SHUTDOWN_SENTINEL: Final[_ShutdownSentinel] = _ShutdownSentinel()


_StatePatchKind = Literal["pipe_start", "pipe_end_success", "pipe_end_error"]


@dataclass(frozen=True)
class _StatePatch:
    """A single Mistral ``Task.update_state`` payload derived from a trace event."""

    kind: _StatePatchKind
    payload: dict[str, Any]


class QueueEventLog(EventLogProtocol):
    """In-process ``EventLogProtocol`` that pushes events onto an asyncio queue.

    Used by the streaming activity to subscribe to per-step trace events
    without persisting them. ``emit`` is called by ``GraphTracer`` from the
    pipe-execution context (which may be a worker thread for inference jobs),
    so the queue insert is always routed via ``loop.call_soon_threadsafe``.

    Best-effort delivery: when the bounded queue is full, events are dropped
    with a one-shot warning. Streaming is observability, not durability.
    """

    def __init__(self, loop: asyncio.AbstractEventLoop, queue: asyncio.Queue[Any]) -> None:
        self._loop = loop
        self._queue = queue
        self._sequence: int = 0
        self._sequence_lock = threading.Lock()
        self._writer_id = "mistralai-workflows-streaming"
        self._closed = False
        self._overflow_warned = False

    @property
    @override
    def writer_id(self) -> str:
        return self._writer_id

    @override
    def next_sequence(self) -> int:
        with self._sequence_lock:
            seq = self._sequence
            self._sequence += 1
            return seq

    @override
    def emit(self, event: TraceEvent) -> None:
        """Push the event onto the queue, routing across threads if needed.

        ``call_soon_threadsafe`` is correct from a worker thread but defers
        execution to the next loop iteration; in our hot path the trace
        events fire on the same loop as the activity, so we ``put_nowait``
        directly to keep the forwarder fed without an extra trampoline.
        """
        if self._closed:
            return
        try:
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            running_loop = None
        if running_loop is self._loop:
            self._enqueue(event)
        else:
            self._loop.call_soon_threadsafe(self._enqueue, event)

    def _enqueue(self, event: TraceEvent) -> None:
        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            if not self._overflow_warned:
                self._overflow_warned = True
                log.warning(
                    f"mistralai_workflows streaming forwarder queue full (maxsize={_QUEUE_MAX_SIZE}); dropping further events for this run.",
                )

    @override
    def read_events(self, pipeline_run_id: str) -> list[TraceEvent]:
        return []

    @override
    def close(self) -> None:
        self._closed = True

    @override
    def cleanup(self, pipeline_run_id: str) -> None:
        return None


def build_streaming_data_inclusion() -> DataInclusionConfig:
    """All-flags-off ``DataInclusionConfig`` for the streaming tracer.

    Phase 2.1 only needs pipe metadata (codes, node ids, output spec name);
    capturing rendered content / stack traces / registry dumps would just
    bloat ``Task.update_state`` payloads with no consumer benefit.
    """
    return DataInclusionConfig(
        stuff_json_content=False,
        stuff_text_content=False,
        stuff_html_content=False,
        error_stack_traces=False,
        pipe_and_concept_registry=False,
    )


def _state_patch_for_pipe_start(event: PipeStartEvent, started_steps: int) -> _StatePatch:
    return _StatePatch(
        kind="pipe_start",
        payload={
            "phase": "in_progress",
            "current_step_pipe_code": event.pipe_code,
            "current_step_node_id": event.node_id,
            "last_event_kind": "pipe_start",
            "started_steps": started_steps,
        },
    )


def _state_patch_for_pipe_end_success(event: PipeEndSuccessEvent, completed_steps: int) -> _StatePatch:
    output_stuff_name: str | None = None
    if event.output_spec is not None:
        output_stuff_name = event.output_spec.name
    return _StatePatch(
        kind="pipe_end_success",
        payload={
            "phase": "in_progress",
            "last_event_kind": "pipe_end_success",
            "completed_steps": completed_steps,
            "last_output_stuff_name": output_stuff_name,
        },
    )


def _state_patch_for_pipe_end_error(event: PipeEndErrorEvent) -> _StatePatch:
    return _StatePatch(
        kind="pipe_end_error",
        payload={
            "phase": "in_progress",
            "last_event_kind": "pipe_end_error",
            "current_step_node_id": event.node_id,
        },
    )


def map_trace_event_to_state_patch(
    event: TraceEvent,
    started_steps: int,
    completed_steps: int,
) -> _StatePatch | None:
    """Map a trace event to a ``Task.update_state`` patch, or ``None`` to skip.

    Phase 2.1 surfaces only pipe-step boundaries (``PipeStartEvent`` /
    ``PipeEndSuccessEvent`` / ``PipeEndErrorEvent``). The other trace event
    kinds (edges, batch fan-out, controller outputs, execution metadata,
    usage reports) are intentionally suppressed — they fire too frequently
    to be useful as Mistral state updates and are already captured by
    Pipelex's own reporting / graph infrastructure.

    Mirrors the ``isinstance``-chain pattern used in
    ``pipelex.tracing.graphspec_assembler`` for the same union of subclasses.
    """
    if isinstance(event, PipeStartEvent):
        return _state_patch_for_pipe_start(event=event, started_steps=started_steps)
    if isinstance(event, PipeEndSuccessEvent):
        return _state_patch_for_pipe_end_success(event=event, completed_steps=completed_steps)
    if isinstance(event, PipeEndErrorEvent):
        return _state_patch_for_pipe_end_error(event=event)
    if isinstance(
        event,
        (
            EdgeEvent,
            ControllerOutputEvent,
            BatchItemEvent,
            BatchAggregateEvent,
            ParallelCombineEvent,
            ExecutionDataEvent,
            UsageReportEvent,
        ),
    ):
        return None
    log.warning(f"Streaming forwarder received unknown trace event type: {type(event).__name__}")
    return None


async def forward_events_to_task(
    event_queue: asyncio.Queue[Any],
    update_state: Callable[[dict[str, Any]], Awaitable[None]],
) -> None:
    """Drain the event queue, translating each trace event into a state update.

    Runs concurrently with ``run_pipe_via_bridge`` and terminates when the
    sentinel is observed. Maintains running counters for ``started_steps`` and
    ``completed_steps`` so each emitted patch carries the cumulative count
    after the event itself (1-indexed: the first PIPE_START reports
    ``started_steps=1``).

    The caller is responsible for posting ``SHUTDOWN_SENTINEL`` and awaiting
    this coroutine before letting the parent ``Task`` async-context exit, so
    the final per-step ``update_state`` calls are flushed before
    ``Task.__aexit__`` closes the task.
    """
    started_steps = 0
    completed_steps = 0
    while True:
        item = await event_queue.get()
        if isinstance(item, _ShutdownSentinel):
            return
        if not isinstance(item, TraceEvent):
            log.warning(f"Streaming forwarder received unexpected queue item type: {type(item).__name__}")
            continue

        next_started = started_steps + 1 if isinstance(item, PipeStartEvent) else started_steps
        next_completed = completed_steps + 1 if isinstance(item, PipeEndSuccessEvent) else completed_steps
        patch = map_trace_event_to_state_patch(
            event=item,
            started_steps=next_started,
            completed_steps=next_completed,
        )
        if patch is None:
            continue
        started_steps = next_started
        completed_steps = next_completed
        await update_state(patch.payload)


def get_drain_timeout_seconds() -> float:
    """Expose the forwarder drain timeout for streaming.py to use in wait_for."""
    return _FORWARDER_DRAIN_TIMEOUT_SECONDS


def get_queue_max_size() -> int:
    """Expose the queue max size for streaming.py to use when constructing the queue."""
    return _QUEUE_MAX_SIZE
