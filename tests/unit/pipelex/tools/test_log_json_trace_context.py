"""The ``json`` sink writes the trace context of the span current when a record is logged.

The keys are the ones OpenTelemetry specifies for trace context in a JSON log that is not OTLP,
``trace_id``, ``span_id`` and ``trace_flags``, lowercase hex at their full widths, and a record logged
outside any valid span carries none of them. A boot line held until the sink arrives keeps the span it
was logged in. The records go the whole way, from the facade through the module-named logger to the
sink's handler, on a fresh ``Log`` so the installed sink is the one under test and the teardown leaves
the root logger as it found it.
"""

from __future__ import annotations

import io
import json
import logging
import re
from typing import TYPE_CHECKING, Any

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.trace import NonRecordingSpan, SpanContext, TraceFlags

from pipelex.system.configuration.config_loader import ConfigLoader
from pipelex.tools.log.json_log_sink import (
    LOGGER_KEY,
    MESSAGE_KEY,
    SEVERITY_KEY,
    SPAN_ID_KEY,
    TIME_KEY,
    TRACE_FLAGS_KEY,
    TRACE_ID_KEY,
    JsonLogSink,
)
from pipelex.tools.log.log import Log
from pipelex.tools.log.log_config import LogConfig
from pipelex.tools.log.log_fields import COLLIDING_FIELD_PREFIX
from pipelex.tools.misc.toml_utils import load_toml_from_path

if TYPE_CHECKING:
    from collections.abc import Iterator

TRACE_KEYS: tuple[str, ...] = (TRACE_ID_KEY, SPAN_ID_KEY, TRACE_FLAGS_KEY)

# A span context whose ids are small enough that only a full-width, zero-padded spelling gets them right,
# and which is not sampled, so its flags are written as they are rather than as the sampled default.
_UNSAMPLED_SPAN_CONTEXT = SpanContext(trace_id=0xAB, span_id=0xCD, is_remote=False, trace_flags=TraceFlags(TraceFlags.DEFAULT))


def _package_log_config() -> LogConfig:
    config_dict = load_toml_from_path(ConfigLoader().pipelex_root_dir / "pipelex.toml")
    return LogConfig.model_validate(config_dict["runtime"]["log"])


def _own_lines(buffer: io.StringIO) -> list[dict[str, Any]]:
    """Every line this module emitted, each parsed as one JSON object, whatever else the process logged meanwhile."""
    lines = [json.loads(line) for line in buffer.getvalue().splitlines() if line]
    return [line for line in lines if line[LOGGER_KEY] == __name__]


class TestJsonSinkTraceContext:
    @pytest.fixture
    def json_log(self, caplog: pytest.LogCaptureFixture) -> Iterator[tuple[Log, io.StringIO]]:
        """A fresh ``Log`` with the json sink installed on a buffer, torn down so the root logger is left as found."""
        # pytest's ``log_level`` option restores the root logger's level at every phase boundary, undoing the
        # level ``configure`` sets from inside a fixture; the module's own logger is enabled explicitly and
        # ``caplog`` restores it at teardown.
        caplog.set_level(logging.INFO, logger=__name__)
        buffer = io.StringIO()
        fresh = Log()
        fresh.configure(log_config=_package_log_config())
        fresh.install_sink(JsonLogSink(stream=buffer))
        try:
            yield fresh, buffer
        finally:
            fresh.reset()

    def test_a_line_logged_inside_a_span_carries_its_trace_context_in_hex(self, json_log: tuple[Log, io.StringIO]) -> None:
        fresh, buffer = json_log
        tracer = TracerProvider().get_tracer(__name__)
        with tracer.start_as_current_span("work") as span:
            fresh.info("inside")
        span_context = span.get_span_context()

        (line,) = _own_lines(buffer)
        assert line[TRACE_ID_KEY] == f"{span_context.trace_id:032x}"
        assert line[SPAN_ID_KEY] == f"{span_context.span_id:016x}"
        assert line[TRACE_FLAGS_KEY] == "01"
        assert re.fullmatch(r"[0-9a-f]{32}", line[TRACE_ID_KEY])
        assert re.fullmatch(r"[0-9a-f]{16}", line[SPAN_ID_KEY])

    def test_a_line_logged_outside_any_span_carries_none_of_the_keys(self, json_log: tuple[Log, io.StringIO]) -> None:
        fresh, buffer = json_log
        fresh.info("outside")

        (line,) = _own_lines(buffer)
        assert not set(TRACE_KEYS) & set(line)

    def test_an_invalid_current_span_writes_nothing(self, json_log: tuple[Log, io.StringIO]) -> None:
        """A context can hold a span that names no trace; a line under it is a line outside any span."""
        fresh, buffer = json_log
        with trace.use_span(trace.INVALID_SPAN):
            fresh.info("under the invalid span")

        (line,) = _own_lines(buffer)
        assert not set(TRACE_KEYS) & set(line)

    def test_the_ids_are_zero_padded_and_the_flags_written_as_they_are(self, json_log: tuple[Log, io.StringIO]) -> None:
        fresh, buffer = json_log
        with trace.use_span(NonRecordingSpan(_UNSAMPLED_SPAN_CONTEXT)):
            fresh.info("unsampled")

        (line,) = _own_lines(buffer)
        assert line[TRACE_ID_KEY] == "000000000000000000000000000000ab"
        assert line[SPAN_ID_KEY] == "00000000000000cd"
        assert line[TRACE_FLAGS_KEY] == "00"

    def test_the_line_leaving_the_span_no_longer_carries_it(self, json_log: tuple[Log, io.StringIO]) -> None:
        fresh, buffer = json_log
        tracer = TracerProvider().get_tracer(__name__)
        with tracer.start_as_current_span("outer") as outer:
            with tracer.start_as_current_span("inner") as inner:
                fresh.info("in the inner span")
            fresh.info("back in the outer span")
        fresh.info("after both")

        in_inner, in_outer, after = _own_lines(buffer)
        assert in_inner[SPAN_ID_KEY] == f"{inner.get_span_context().span_id:016x}"
        assert in_outer[SPAN_ID_KEY] == f"{outer.get_span_context().span_id:016x}"
        assert in_inner[TRACE_ID_KEY] == in_outer[TRACE_ID_KEY]
        assert not set(TRACE_KEYS) & set(after)

    def test_the_trace_keys_follow_the_fixed_keys_and_precede_the_fields(self, json_log: tuple[Log, io.StringIO]) -> None:
        fresh, buffer = json_log
        with trace.use_span(NonRecordingSpan(_UNSAMPLED_SPAN_CONTEXT)):
            fresh.info("ordered", fields={"files": 7})

        (line,) = _own_lines(buffer)
        assert list(line) == [TIME_KEY, SEVERITY_KEY, LOGGER_KEY, MESSAGE_KEY, TRACE_ID_KEY, SPAN_ID_KEY, TRACE_FLAGS_KEY, "files"]

    def test_the_trace_keys_are_reserved_with_or_without_a_span(self, json_log: tuple[Log, io.StringIO]) -> None:
        """A field named like a trace key is prefixed on every line, so its wire name never depends on a span being current."""
        fresh, buffer = json_log
        supplied = dict.fromkeys(TRACE_KEYS, "supplied")
        fresh.info("no span", fields=supplied)
        with trace.use_span(NonRecordingSpan(_UNSAMPLED_SPAN_CONTEXT)):
            fresh.info("in a span", fields=supplied)

        without_span, with_span = _own_lines(buffer)
        for key in TRACE_KEYS:
            assert key not in without_span
            assert without_span[f"{COLLIDING_FIELD_PREFIX}{key}"] == "supplied"
            assert with_span[f"{COLLIDING_FIELD_PREFIX}{key}"] == "supplied"
        assert with_span[TRACE_ID_KEY] == "000000000000000000000000000000ab"

    def test_a_boot_line_held_until_the_sink_arrives_keeps_the_span_it_was_logged_in(self, caplog: pytest.LogCaptureFixture) -> None:
        """The holding handler replays each record in the context it was emitted in, not in the one the install runs under."""
        caplog.set_level(logging.INFO, logger=__name__)
        buffer = io.StringIO()
        fresh = Log()
        fresh.configure(log_config=_package_log_config())
        tracer = TracerProvider().get_tracer(__name__)
        try:
            with tracer.start_as_current_span("boot step") as boot_step:
                fresh.info("held inside a span")
            fresh.info("held outside any span")
            with tracer.start_as_current_span("install"):
                fresh.install_sink(JsonLogSink(stream=buffer))
        finally:
            fresh.reset()

        inside, outside = _own_lines(buffer)
        assert inside[SPAN_ID_KEY] == f"{boot_step.get_span_context().span_id:016x}"
        assert not set(TRACE_KEYS) & set(outside)
