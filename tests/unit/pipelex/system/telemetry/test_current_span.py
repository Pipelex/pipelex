"""``span_made_current`` makes a span current for a block and touches nothing else.

The span stays owned by the code that started it: the block never ends it, never records an exception
on it and never sets its status, even when an exception crosses the block while the span is still
recording, and the previous context comes back on the way out, however the block exits. A ``None``
span, which is what the runtime holds when it has no tracer, leaves the context as it was.
"""

from __future__ import annotations

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import Span as SdkSpan
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.trace import StatusCode

from pipelex.system.telemetry.current_span import span_made_current


def _started_span(*, name: str) -> SdkSpan:
    span = TracerProvider().get_tracer(__name__).start_span(name)
    assert isinstance(span, SdkSpan)
    return span


def _fail_under(*, span: SdkSpan) -> None:
    with span_made_current(span=span):
        msg = "boom"
        raise ValueError(msg)


class TestSpanMadeCurrent:
    def test_the_span_is_current_inside_the_block_and_the_previous_one_comes_back(self) -> None:
        outer = _started_span(name="outer")
        span = _started_span(name="work")

        with trace.use_span(outer):
            with span_made_current(span=span):
                assert trace.get_current_span() is span
            assert trace.get_current_span() is outer
        assert span.is_recording()

    def test_an_exception_crossing_the_block_leaves_the_span_as_it_was(self) -> None:
        span = _started_span(name="work")

        with pytest.raises(ValueError, match="boom"):
            _fail_under(span=span)

        assert trace.get_current_span() is trace.INVALID_SPAN
        assert span.is_recording()
        assert span.status.status_code is StatusCode.UNSET
        assert list(span.events) == []

    def test_a_none_span_leaves_the_context_alone(self) -> None:
        caller = _started_span(name="caller")

        with trace.use_span(caller), span_made_current(span=None):
            assert trace.get_current_span() is caller
