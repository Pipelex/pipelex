"""``pipelex_span_active`` holds a Pipelex span for a block, where the ``pipelex.*`` log fields read it.

OpenTelemetry's current context is never touched: inside the block the current span is whatever it was
outside, the host's or none. The span stays owned by the code that started it: the block never ends it,
never records an exception on it and never sets its status, even when an exception crosses the block
while the span is still recording, and the previous Pipelex span comes back on the way out, however the
block exits. A ``None`` span, which is what the runtime holds when it has no tracer, and a span naming
no trace, which is what a no-op tracer starts, hold nothing.
"""

from __future__ import annotations

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import Span as SdkSpan
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.trace import StatusCode

from pipelex.system.telemetry.current_span import pipelex_span_active, pipelex_span_context_for_logs


def _started_span(*, name: str) -> SdkSpan:
    span = TracerProvider().get_tracer(__name__).start_span(name)
    assert isinstance(span, SdkSpan)
    return span


def _fail_under(*, span: SdkSpan) -> None:
    with pipelex_span_active(span=span):
        msg = "boom"
        raise ValueError(msg)


class TestPipelexSpanActive:
    def test_the_innermost_pipelex_span_is_held_inside_the_block_and_the_previous_one_after(self) -> None:
        outer = _started_span(name="outer")
        inner = _started_span(name="inner")

        with pipelex_span_active(span=outer):
            with pipelex_span_active(span=inner):
                assert pipelex_span_context_for_logs() == inner.get_span_context()
            assert pipelex_span_context_for_logs() == outer.get_span_context()
        assert pipelex_span_context_for_logs() is None
        assert inner.is_recording()

    def test_opentelemetrys_current_span_is_never_touched(self) -> None:
        host = _started_span(name="host")
        pipelex_span = _started_span(name="pipe")

        with pipelex_span_active(span=pipelex_span):
            assert trace.get_current_span() is trace.INVALID_SPAN
        with trace.use_span(host), pipelex_span_active(span=pipelex_span):
            assert trace.get_current_span() is host

    def test_an_exception_crossing_the_block_leaves_the_span_as_it_was(self) -> None:
        span = _started_span(name="work")

        with pytest.raises(ValueError, match="boom"):
            _fail_under(span=span)

        assert pipelex_span_context_for_logs() is None
        assert span.is_recording()
        assert span.status.status_code is StatusCode.UNSET
        assert list(span.events) == []

    def test_a_none_span_holds_nothing(self) -> None:
        enclosing = _started_span(name="enclosing")

        with pipelex_span_active(span=None):
            assert pipelex_span_context_for_logs() is None
        with pipelex_span_active(span=enclosing), pipelex_span_active(span=None):
            assert pipelex_span_context_for_logs() == enclosing.get_span_context()

    def test_a_span_naming_no_trace_does_not_hide_the_enclosing_pipelex_span(self) -> None:
        """What a no-op tracer starts, under ``OTEL_SDK_DISABLED`` for one, must not hide a valid span."""
        enclosing = _started_span(name="enclosing")

        with pipelex_span_active(span=trace.INVALID_SPAN):
            assert pipelex_span_context_for_logs() is None
        with pipelex_span_active(span=enclosing), pipelex_span_active(span=trace.INVALID_SPAN):
            assert pipelex_span_context_for_logs() == enclosing.get_span_context()
