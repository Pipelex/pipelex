"""The Pipelex span active in this task, which a log line is joined to.

The runtime starts its spans with an explicit parent carried in the job metadata, because a run's trace
is derived from its business identifiers and has to survive a process boundary, where an in-process
context does not travel. A span started that way is current nowhere, and the runtime never makes it
OpenTelemetry's current span: Pipelex's tracer is its own and never the process's global one, so one of
its spans made current there would re-parent the host application's own instrumentation under a trace
only Pipelex's exporters receive, and have a sampler that follows its parent keep it. Instead, the
runtime holds the span in a context variable of its own while the work it measures runs, in this task
and in whatever copies the task's context, a thread started by ``asyncio.to_thread`` or a boot line the
holding handler replays, and restores the previous value on the way out. The log sinks read it to write
a line's trace context, and nothing else does.

Holding a span never ends it, records an exception on it or sets its status, which stay with the code
that started it, and it never becomes the way a parent reaches a child: the job metadata still carries
that, so a child running in another process gets the same parent it always did.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import TYPE_CHECKING

from opentelemetry import trace
from opentelemetry.context import get_current

if TYPE_CHECKING:
    from collections.abc import Generator

    from opentelemetry.context import Context
    from opentelemetry.trace import Span, SpanContext

# The Pipelex span active here; only ever a span naming a trace, since ``pipelex_span_active`` sets no other.
_ACTIVE_PIPELEX_SPAN: ContextVar[Span | None] = ContextVar("pipelex_active_span", default=None)


@contextmanager
def pipelex_span_active(*, span: Span | None) -> Generator[None]:
    """Hold ``span`` as the Pipelex span active here while the block runs; no span, or one naming no trace, holds nothing.

    ``None`` is what the runtime holds with no tracer or in a dry run. A span naming no trace is what a
    no-op tracer starts, under ``OTEL_SDK_DISABLED`` for one, and holding it would hide the enclosing
    Pipelex span, or the host's current one, from every line of the block. OpenTelemetry's own context is
    left as it is either way.
    """
    if span is None or not span.get_span_context().is_valid:
        yield
        return
    token = _ACTIVE_PIPELEX_SPAN.set(span)
    try:
        yield
    finally:
        _ACTIVE_PIPELEX_SPAN.reset(token)


def span_context_for_logs() -> SpanContext | None:
    """The span a line logged here is joined to: the active Pipelex span, else OpenTelemetry's current span, else none.

    The current span is only read, so a line logged under the host's own span, outside any Pipelex run,
    still joins the host's trace.
    """
    pipelex_span = _ACTIVE_PIPELEX_SPAN.get()
    if pipelex_span is not None:
        return pipelex_span.get_span_context()
    current_span_context = trace.get_current_span().get_span_context()
    if current_span_context.is_valid:
        return current_span_context
    return None


def otel_context_for_logs() -> Context:
    """The context a log record is emitted in: the current one with the active Pipelex span in it, or the current one as is.

    Built for the one record and never attached, so OpenTelemetry's current context stays what it was.
    """
    pipelex_span = _ACTIVE_PIPELEX_SPAN.get()
    if pipelex_span is None:
        return get_current()
    return trace.set_span_in_context(pipelex_span)
