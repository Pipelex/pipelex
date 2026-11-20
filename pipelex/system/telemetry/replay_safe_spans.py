"""Pipe spans opened in replayable workflow code: one span per pipe, with its true start, across a replay.

An orchestrator such as Temporal runs a controller pipe inline in its workflow code and re-executes that code
from the start whenever it replays the workflow (see ``pipelex.system.telemetry.workflow_execution``). A span
opened there follows three rules, which ``PipeAbstract`` applies when a pipe span starts and ends:

- **Its id comes from the workflow's deterministic random**, through ``ReplaySafeIdGenerator``
  (``pipelex.system.telemetry.replay_safe_id_generator``), the id generator of Pipelex's tracer provider, so a
  replay recomputes the id the live execution gave it, and the spans its children opened, in workflow code or in
  an activity, still point at a parent that exists. Only a pipe span draws from that random, inside
  ``opening_pipe_span``: a span of any other kind opened in workflow code keeps a random id, so whether such a span
  exists, which can depend on a worker's configuration, never shifts the ids of the pipe spans after it.
- **Its start and its end are read on the workflow's clock**, so a replay recomputes its start, and a pipe whose
  workflow crossed an eviction keeps the start it had before the eviction. That clock is the time of the workflow
  task being processed, so a pipe span's times are as fine as the workflow's tasks: a pipe that starts and ends in
  one task lasts zero.
- **Only the live execution ends it**, which is what exports it: an end reached while the workflow code replays
  history was already exported by the execution that ran it first, and an end reached because the workflow code is
  unwinding (``WorkflowExecutionProtocol.is_unwinding``), on an eviction or a workflow task the orchestrator retries,
  is not the pipe's real end, which a later execution reaches and exports.

The rules hold for a tracer that can keep them, whose provider draws ids through ``ReplaySafeIdGenerator``
(``TelemetryManagerAbstract.is_otel_tracer_replay_safe``), which Pipelex's own telemetry manager's always does. A
tracer an injected telemetry manager hands out from another provider cannot recompute an id on a replay, so its spans
keep the wall clock and every end, as if nothing replayed.

Outside workflow code, which is every span of a process that runs no orchestrator and every span opened in an
activity, nothing changes: ids are random and times are the wall clock.

The model is ``temporalio.contrib.opentelemetry``'s replay-safe tracer provider, with one difference: it reads the
workflow's clock for a span's start only on a replay, so its spans start at the wall clock live and at the workflow
task's time once replayed, whereas these always start and end on the workflow's clock, which keeps one start
whichever execution exports the span.
"""

import contextlib
from collections.abc import Generator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import NamedTuple

from pipelex.system.telemetry.telemetry_manager_abstract import TelemetryManagerAbstract
from pipelex.system.telemetry.workflow_execution import WorkflowExecutionProtocol, get_workflow_execution, workflow_execution_slot
from pipelex.tools.log.error_fields import error_fields
from pipelex.tools.log.log import log

_is_opening_pipe_span: ContextVar[bool] = ContextVar("is_opening_pipe_span", default=False)


class PipeEnd(NamedTuple):
    """How a pipe ending now ends: whether this is its real end, and the time it ends at."""

    is_real_end: bool
    """True when the live execution reached the pipe's real end, which is logged and exports its span."""
    end_time_ns: int | None
    """The workflow's clock in workflow code, ``None`` (the wall clock) elsewhere or when it is no real end."""


_NOT_A_REAL_END = PipeEnd(is_real_end=False, end_time_ns=None)
_REAL_END_ON_THE_WALL_CLOCK = PipeEnd(is_real_end=True, end_time_ns=None)


@contextmanager
def opening_pipe_span() -> Generator[None, None, None]:
    """The block a pipe span is opened in, whose span id ``ReplaySafeIdGenerator`` draws from the workflow's random."""
    token = _is_opening_pipe_span.set(True)
    try:
        yield
    finally:
        _is_opening_pipe_span.reset(token)


def get_pipe_span_workflow_execution() -> WorkflowExecutionProtocol | None:
    """The workflow code a pipe span opening now runs in, ``None`` for a span of another kind or outside workflow code."""
    if not _is_opening_pipe_span.get():
        return None
    return get_workflow_execution()


def _get_span_workflow_execution() -> WorkflowExecutionProtocol | None:
    """The workflow code a pipe span runs in, when the tracer can keep the replay-safe rules, ``None`` otherwise."""
    if not TelemetryManagerAbstract.is_instance_tracer_replay_safe():
        return None
    return get_workflow_execution()


def pipe_span_start_time_ns() -> int | None:
    """The time a pipe span opened now starts at: the workflow's clock in workflow code, ``None`` (the wall clock) elsewhere."""
    workflow_execution = _get_span_workflow_execution()
    if workflow_execution is None:
        return None
    return workflow_execution.time_ns()


def is_replaying_workflow_code() -> bool:
    """Whether the current call re-executes workflow code whose history a previous execution already ran."""
    workflow_execution = get_workflow_execution()
    return workflow_execution is not None and workflow_execution.is_replaying()


def resolve_pipe_span_end(*, error: BaseException | None = None) -> PipeEnd:
    """How a pipe span ending now, on ``error`` if it failed, ends: exported at its time, or left open and dropped.

    Always a real end on the wall clock outside workflow code, and for a tracer that cannot keep the replay-safe rules.

    Args:
        error: The exception the pipe ends on, or None when it succeeded.

    Returns:
        Whether the span is ended, which exports it, and the time it ends at.
    """
    return _resolve_pipe_end(error=error, is_span=True)


def is_real_pipe_end(*, error: BaseException | None = None) -> bool:
    """Whether a pipe ending now, on ``error`` if it failed, is its real end, reached by the live execution.

    The test a pipe's run summary is logged under, whatever the tracer: a replay of workflow code, which a previous
    execution already logged, and an unwinding of it, after which the pipe runs again, log nothing.

    Args:
        error: The exception the pipe ends on, or None when it succeeded.

    Returns:
        True outside workflow code, and in it when the live execution reached the pipe's real end.
    """
    return _resolve_pipe_end(error=error, is_span=False).is_real_end


def _resolve_pipe_end(*, error: BaseException | None, is_span: bool) -> PipeEnd:
    """The pipe's end, asking the orchestrator's probe without letting it replace the exception the pipe ends on.

    On a failure the call runs inside the pipe's ``except BaseException``, possibly while the orchestrator tears the
    workflow code down, where a probe may raise rather than answer: such an end is not counted, and the pipe's own
    exception goes on as it came. On success, a probe that raises is a fault of its plugin, and propagates.
    """
    if error is None:
        return _ask_probe(error=None, is_span=is_span)
    if isinstance(error, GeneratorExit) and workflow_execution_slot.is_claimed:
        # A coroutine closed without finishing, as an orchestrator's teardown closes its workflow code's coroutines,
        # possibly from another thread: never a pipe's end, and answered before the probe is asked anything.
        return _NOT_A_REAL_END
    try:
        return _ask_probe(error=error, is_span=is_span)
    except Exception as probe_error:  # ruff: ignore[blind-except]
        # (2) The probe is a boot-orchestrator plugin's code, whose exception surface cannot be enumerated, asked while
        # the pipe's own exception propagates, which it must not replace. The end is not counted.
        # (2) The warning goes through whatever handlers the host installed, which may refuse it; the pipe's exception
        # still goes on as it came.
        with contextlib.suppress(Exception):
            log.warning("A failed pipe's end was not counted: the workflow probe failed", fields=error_fields(exc=probe_error))
        return _NOT_A_REAL_END


def _ask_probe(*, error: BaseException | None, is_span: bool) -> PipeEnd:
    workflow_execution = _get_span_workflow_execution() if is_span else get_workflow_execution()
    if workflow_execution is None:
        return _REAL_END_ON_THE_WALL_CLOCK
    # Unwinding first: it is the question an orchestrator tearing its workflow code down can always answer.
    if error is not None and workflow_execution.is_unwinding(error=error):
        return _NOT_A_REAL_END
    if workflow_execution.is_replaying():
        return _NOT_A_REAL_END
    if not is_span:
        return _REAL_END_ON_THE_WALL_CLOCK
    return PipeEnd(is_real_end=True, end_time_ns=workflow_execution.time_ns())
