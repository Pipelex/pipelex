"""Pipe spans opened in replayable workflow code: one span per pipe, with its true start, across a replay.

An orchestrator such as Temporal runs a controller pipe inline in its workflow code and re-executes that code
from the start whenever it replays the workflow (see ``pipelex.system.telemetry.workflow_execution``). A span
opened there follows three rules, which ``PipeAbstract`` applies when a pipe span starts and ends:

- **Its id comes from the workflow's deterministic random**, through ``ReplaySafeIdGenerator``
  (``pipelex.system.telemetry.replay_safe_id_generator``), the id generator of Pipelex's tracer provider, so a
  replay recomputes the id the live execution gave it, and the spans its children opened, in workflow code or in
  an activity, still point at a parent that exists.
- **Its start and its end are read on the workflow's clock**, so a replay recomputes its start, and a pipe whose
  workflow crossed an eviction keeps the start it had before the eviction.
- **Only the live execution ends it**, which is what exports it: an end reached while the workflow code replays
  history was already exported by the execution that ran it first, and an end reached because the orchestrator
  is unwinding the workflow code, on an eviction or a retried workflow task, is not the pipe's real end, which a
  later execution reaches and exports.

Outside workflow code, which is every span of a process that runs no orchestrator and every span opened in an
activity, nothing changes: ids are random and times are the wall clock.

The model is ``temporalio.contrib.opentelemetry``'s replay-safe tracer provider, with one difference: it reads the
workflow's clock for a span's start only on a replay, so its spans start at the wall clock live and at the workflow
task's time once replayed, whereas these always start and end on the workflow's clock, which keeps one start
whichever execution exports the span.
"""

from typing import TYPE_CHECKING

from pipelex.system.telemetry.workflow_execution import get_workflow_execution

if TYPE_CHECKING:
    from opentelemetry.trace import Span


def workflow_time_ns() -> int | None:
    """The time a span opened or ended now takes: the workflow's clock in workflow code, ``None`` (the wall clock) elsewhere."""
    workflow_execution = get_workflow_execution()
    if workflow_execution is None:
        return None
    return workflow_execution.time_ns()


def is_span_end_exported(*, error: BaseException | None = None) -> bool:
    """Whether a span ending now, on ``error`` if it failed, is the pipe's real end, which exports it.

    Always true outside workflow code. In workflow code, false while the workflow replays history, whose spans the
    execution that first ran it exported, and false on an error that is the orchestrator unwinding the workflow
    code, whose pipes a later execution runs to their real end.

    Args:
        error: The exception the span ends on, or None when the pipe succeeded.

    Returns:
        True when the span should be ended, which exports it, and False when it must be left open and dropped.
    """
    workflow_execution = get_workflow_execution()
    if workflow_execution is None:
        return True
    if workflow_execution.is_replaying():
        return False
    return error is None or not workflow_execution.is_unwinding(error=error)


def end_span(*, span: "Span") -> None:
    """End ``span`` on the workflow's clock in workflow code and on the wall clock elsewhere.

    The caller has already asked ``is_span_end_exported``, before spending anything on the span's last attributes.
    """
    span.end(end_time=workflow_time_ns())
