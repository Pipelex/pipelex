"""Pipe spans opened in replayable workflow code: one span per pipe, with its true start, across a replay.

An orchestrator such as Temporal runs a controller pipe inline in its workflow code and re-executes that code
from the start whenever it replays the workflow (see ``pipelex.system.telemetry.workflow_execution``). A span
opened there follows these rules, which ``PipeAbstract`` applies when a pipe span starts and ends:

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
from pipelex.system.telemetry.workflow_execution import WorkflowExecutionProtocol, get_workflow_execution
from pipelex.tools.log.error_fields import error_fields
from pipelex.tools.log.log import log

_is_opening_pipe_span: ContextVar[bool] = ContextVar("is_opening_pipe_span", default=False)


class PipeEnd(NamedTuple):
    """How a pipe ending now ends: whether this is its real end, and the time it ends at."""

    is_real_end: bool
    """True when the live execution reached the pipe's real end, which exports its span."""
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
    """The workflow code a pipe span opening now runs in, ``None`` for a span of another kind or outside workflow code.

    Also ``None`` for a tracer that cannot keep the replay-safe rules, so a span's id is drawn from the workflow's random
    under the same test that reads its start and its end on the workflow's clock.
    """
    if not _is_opening_pipe_span.get():
        return None
    return _get_span_workflow_execution()


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


def resolve_pipe_span_end(*, error: BaseException | None = None) -> PipeEnd:
    """How a pipe span ending now, on ``error`` if it failed, ends: exported at its time, or left open and dropped.

    Always a real end on the wall clock outside workflow code, and for a tracer that cannot keep the replay-safe rules.
    The orchestrator's probe is asked without letting it change how the pipe ends: on a failure the call runs inside the
    pipe's ``except BaseException``, possibly while the orchestrator tears the workflow code down, and on a success the
    pipe's output is already made, so a probe that raises rather than answers leaves the end uncounted, and the pipe's
    own exception or result goes on as it came.

    Args:
        error: The exception the pipe ends on, or None when it succeeded.

    Returns:
        Whether the span is ended, which exports it, and the time it ends at.
    """
    try:
        return _ask_probe(error=error)
    except Exception as probe_error:  # ruff: ignore[blind-except]
        # (2) The probe is a boot-orchestrator plugin's code, whose exception surface cannot be enumerated, asked as the
        # pipe ends, whose own result or exception it must not replace. The end is not counted.
        # (2) The warning goes through whatever handlers the host installed, which may refuse it; the pipe's result or
        # exception still goes on as it came.
        with contextlib.suppress(Exception):
            log.warning("A pipe's end was not counted: the workflow probe failed", fields=error_fields(exc=probe_error))
        return _NOT_A_REAL_END


def _ask_probe(*, error: BaseException | None) -> PipeEnd:
    workflow_execution = _get_span_workflow_execution()
    if workflow_execution is None:
        return _REAL_END_ON_THE_WALL_CLOCK
    if isinstance(error, GeneratorExit):
        # A coroutine of workflow code closed without finishing, as an orchestrator's teardown closes them, possibly
        # from another thread: never a pipe's end, and answered before the workflow execution is asked anything.
        return _NOT_A_REAL_END
    # Unwinding first: it is the question an orchestrator tearing its workflow code down can always answer.
    if error is not None and workflow_execution.is_unwinding(error=error):
        return _NOT_A_REAL_END
    if workflow_execution.is_replaying():
        return _NOT_A_REAL_END
    return PipeEnd(is_real_end=True, end_time_ns=workflow_execution.time_ns())
