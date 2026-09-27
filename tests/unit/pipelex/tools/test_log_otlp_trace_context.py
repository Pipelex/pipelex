"""The ``otlp`` sink files each record under OpenTelemetry's current span, and names the Pipelex span beside it.

The sink hands the SDK the current context, from which the SDK takes the record's trace id, span id and
flags, so a collector files the record under the host's own span, or under none when it names no trace.
The Pipelex span held at the log call, a pipe's or an LLM call's, rides as the ``pipelex.trace_id`` and
``pipelex.span_id`` attributes, in hex, and is absent outside one. A boot line held until the sink
arrives keeps both the spans it was logged in. The sink is built on a synchronous processor so each
record is exported before the assertion reads it.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import pytest
from opentelemetry.sdk._logs.export import InMemoryLogExporter, SimpleLogRecordProcessor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.trace import INVALID_SPAN_ID, INVALID_TRACE_ID

from pipelex.system.configuration.config_loader import ConfigLoader
from pipelex.system.telemetry.current_span import PIPELEX_SPAN_ID_KEY, PIPELEX_TRACE_ID_KEY, pipelex_span_active
from pipelex.tools.log.log import Log
from pipelex.tools.log.log_config import LogConfig
from pipelex.tools.log.log_fields import COLLIDING_FIELD_PREFIX
from pipelex.tools.log.otlp_log_sink import OtlpLogSink
from pipelex.tools.misc.toml_utils import load_toml_from_path

if TYPE_CHECKING:
    from collections.abc import Iterator

    from opentelemetry.sdk._logs import LogRecord

PIPELEX_TRACE_KEYS: tuple[str, ...] = (PIPELEX_TRACE_ID_KEY, PIPELEX_SPAN_ID_KEY)


def _package_log_config() -> LogConfig:
    config_dict = load_toml_from_path(ConfigLoader().pipelex_root_dir / "pipelex.toml")
    return LogConfig.model_validate(config_dict["runtime"]["log"])


def _own_records(exporter: InMemoryLogExporter) -> list[LogRecord]:
    """The records this module emitted, whatever else the process logged meanwhile."""
    return [log_data.log_record for log_data in exporter.get_finished_logs() if log_data.instrumentation_scope.name == __name__]


def _attributes(record: LogRecord) -> dict[str, object]:
    return dict(record.attributes or {})


class TestOtlpSinkTraceContext:
    @pytest.fixture
    def otlp_log(self, caplog: pytest.LogCaptureFixture) -> Iterator[tuple[Log, InMemoryLogExporter]]:
        """A fresh ``Log`` with the otlp sink installed on an in-memory exporter, torn down so the root logger is left as found."""
        caplog.set_level(logging.INFO, logger=__name__)
        exporter = InMemoryLogExporter()
        fresh = Log()
        fresh.configure(log_config=_package_log_config())
        fresh.install_sink(OtlpLogSink(processor=SimpleLogRecordProcessor(exporter)))
        try:
            yield fresh, exporter
        finally:
            fresh.reset()

    def test_a_record_outside_a_run_under_a_host_span_is_filed_under_it_with_no_pipelex_attributes(
        self, otlp_log: tuple[Log, InMemoryLogExporter]
    ) -> None:
        fresh, exporter = otlp_log
        tracer = TracerProvider().get_tracer(__name__)
        with tracer.start_as_current_span("work") as span:
            fresh.info("inside")
        span_context = span.get_span_context()

        (inside,) = _own_records(exporter)
        assert inside.trace_id == span_context.trace_id
        assert inside.span_id == span_context.span_id
        assert inside.trace_flags == span_context.trace_flags
        assert not set(PIPELEX_TRACE_KEYS) & set(_attributes(inside))

    def test_a_record_in_a_run_under_a_host_span_is_filed_under_the_host_span_and_names_the_pipelex_one(
        self, otlp_log: tuple[Log, InMemoryLogExporter]
    ) -> None:
        fresh, exporter = otlp_log
        tracer = TracerProvider().get_tracer(__name__)
        pipelex_span = tracer.start_span("pipe")
        with tracer.start_as_current_span("host") as host_span, pipelex_span_active(span=pipelex_span):
            fresh.info("in the pipe")
        host_context = host_span.get_span_context()
        pipelex_context = pipelex_span.get_span_context()

        (in_pipe,) = _own_records(exporter)
        assert in_pipe.trace_id == host_context.trace_id
        assert in_pipe.span_id == host_context.span_id
        assert in_pipe.trace_flags == host_context.trace_flags
        attributes = _attributes(in_pipe)
        assert attributes[PIPELEX_TRACE_ID_KEY] == f"{pipelex_context.trace_id:032x}"
        assert attributes[PIPELEX_SPAN_ID_KEY] == f"{pipelex_context.span_id:016x}"

    def test_a_record_in_a_run_with_no_host_span_is_filed_under_none_and_names_the_pipelex_span(
        self, otlp_log: tuple[Log, InMemoryLogExporter]
    ) -> None:
        fresh, exporter = otlp_log
        pipelex_span = TracerProvider().get_tracer(__name__).start_span("pipe")
        with pipelex_span_active(span=pipelex_span):
            fresh.info("in the pipe")
        pipelex_context = pipelex_span.get_span_context()

        (in_pipe,) = _own_records(exporter)
        assert in_pipe.trace_id == INVALID_TRACE_ID
        assert in_pipe.span_id == INVALID_SPAN_ID
        attributes = _attributes(in_pipe)
        assert attributes[PIPELEX_TRACE_ID_KEY] == f"{pipelex_context.trace_id:032x}"
        assert attributes[PIPELEX_SPAN_ID_KEY] == f"{pipelex_context.span_id:016x}"

    def test_a_record_outside_any_span_carries_neither(self, otlp_log: tuple[Log, InMemoryLogExporter]) -> None:
        fresh, exporter = otlp_log
        fresh.info("outside")

        (outside,) = _own_records(exporter)
        assert outside.trace_id == INVALID_TRACE_ID
        assert outside.span_id == INVALID_SPAN_ID
        assert not set(PIPELEX_TRACE_KEYS) & set(_attributes(outside))

    def test_the_pipelex_keys_are_reserved_with_or_without_a_pipelex_span(self, otlp_log: tuple[Log, InMemoryLogExporter]) -> None:
        """A field named like a ``pipelex.*`` key is prefixed on every record, so its wire name never depends on a span being held."""
        fresh, exporter = otlp_log
        supplied = dict.fromkeys(PIPELEX_TRACE_KEYS, "supplied")
        fresh.info("no span", fields=supplied)
        with pipelex_span_active(span=TracerProvider().get_tracer(__name__).start_span("pipe")):
            fresh.info("in a pipe", fields=supplied)

        without_span, with_span = (_attributes(record) for record in _own_records(exporter))
        for key in PIPELEX_TRACE_KEYS:
            assert key not in without_span
            assert without_span[f"{COLLIDING_FIELD_PREFIX}{key}"] == "supplied"
            assert with_span[f"{COLLIDING_FIELD_PREFIX}{key}"] == "supplied"
            assert with_span[key] != "supplied"

    def test_a_boot_line_held_until_the_sink_arrives_keeps_the_spans_it_was_logged_in(self, caplog: pytest.LogCaptureFixture) -> None:
        """The holding handler replays each record in the context it was emitted in, not in the one the install runs under."""
        caplog.set_level(logging.INFO, logger=__name__)
        exporter = InMemoryLogExporter()
        fresh = Log()
        fresh.configure(log_config=_package_log_config())
        tracer = TracerProvider().get_tracer(__name__)
        pipelex_span = tracer.start_span("pipe at boot")
        try:
            with tracer.start_as_current_span("boot step") as boot_step:
                fresh.info("held inside a span")
            with pipelex_span_active(span=pipelex_span):
                fresh.info("held inside a pipelex span")
            fresh.info("held outside any span")
            with tracer.start_as_current_span("install"), pipelex_span_active(span=tracer.start_span("pipe at install")):
                fresh.install_sink(OtlpLogSink(processor=SimpleLogRecordProcessor(exporter)))
        finally:
            fresh.reset()

        inside, inside_pipelex, outside = _own_records(exporter)
        assert inside.span_id == boot_step.get_span_context().span_id
        assert not set(PIPELEX_TRACE_KEYS) & set(_attributes(inside))
        assert inside_pipelex.span_id == INVALID_SPAN_ID
        assert _attributes(inside_pipelex)[PIPELEX_SPAN_ID_KEY] == f"{pipelex_span.get_span_context().span_id:016x}"
        assert outside.span_id == INVALID_SPAN_ID
        assert not set(PIPELEX_TRACE_KEYS) & set(_attributes(outside))
