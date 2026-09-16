"""The ``otlp`` sink: a record reaches an in-memory log exporter with the fields as attributes.

The sink is built on a synchronous processor so each record is exported before the assertion reads it;
production builds it on the batching processor and the OTLP HTTP exporter instead.
"""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING, Any

import pytest
from opentelemetry._logs import SeverityNumber
from opentelemetry.context import _SUPPRESS_INSTRUMENTATION_KEY, attach, detach, set_value  # pyright: ignore[reportPrivateUsage]
from opentelemetry.sdk._logs.export import InMemoryLogExporter, SimpleLogRecordProcessor
from opentelemetry.semconv._incubating.attributes import code_attributes
from opentelemetry.semconv.attributes import exception_attributes

from pipelex.system.configuration.config_loader import ConfigLoader
from pipelex.tools.log.log import Log
from pipelex.tools.log.log_config import LogConfig
from pipelex.tools.log.otlp_log_sink import FLUSH_TIMEOUT_MILLIS, ExportPathFilter, OtlpLogSink
from pipelex.tools.misc.toml_utils import load_toml_from_path

if TYPE_CHECKING:
    from collections.abc import Iterator

    from opentelemetry.sdk._logs import LogData
    from pytest_mock import MockerFixture


def _package_log_config() -> LogConfig:
    config_dict = load_toml_from_path(ConfigLoader().pipelex_root_dir / "pipelex.toml")
    return LogConfig.model_validate(config_dict["runtime"]["log"])


def _own_logs(exporter: InMemoryLogExporter) -> list[LogData]:
    """The records this module emitted, whatever else the process logged meanwhile."""
    return [log_data for log_data in exporter.get_finished_logs() if log_data.instrumentation_scope.name == __name__]


def _attributes(log_data: LogData) -> dict[str, Any]:
    attributes = log_data.log_record.attributes
    assert attributes is not None
    return dict(attributes)


class TestOtlpLogSink:
    @pytest.fixture
    def otlp_log(self, caplog: pytest.LogCaptureFixture) -> Iterator[tuple[Log, InMemoryLogExporter]]:
        # pytest's ``log_level`` option restores the root logger's level at every phase boundary, undoing the
        # level ``configure`` sets from inside a fixture; the module's own logger is enabled explicitly and
        # ``caplog`` restores it at teardown.
        caplog.set_level(logging.INFO, logger=__name__)
        exporter = InMemoryLogExporter()
        fresh = Log()
        fresh.configure(log_config=_package_log_config())
        fresh.install_sink(OtlpLogSink(processor=SimpleLogRecordProcessor(exporter)))
        try:
            yield fresh, exporter
        finally:
            fresh.reset()

    def test_a_record_reaches_the_exporter_with_the_fields_and_the_context_as_attributes(self, otlp_log: tuple[Log, InMemoryLogExporter]) -> None:
        fresh, exporter = otlp_log
        with fresh.context(request_id="r1", pipe_run_id="pr1"):
            fresh.info("scanned", fields={"files": 7, "ratio": 0.5, "tags": ["a", "b"], "meta": {"k": "v"}})

        (log_data,) = _own_logs(exporter)
        record = log_data.log_record
        assert record.body == "scanned"
        assert record.severity_text == "INFO"
        assert record.severity_number is SeverityNumber.INFO
        attributes = _attributes(log_data)
        assert attributes["files"] == 7
        assert attributes["ratio"] == 0.5
        assert list(attributes["tags"]) == ["a", "b"]
        assert attributes["meta"] == '{"k": "v"}'
        assert attributes["request_id"] == "r1"
        assert attributes["pipe_run_id"] == "pr1"
        assert "pipeline_run_id" not in attributes
        assert attributes[code_attributes.CODE_FILE_PATH] == __file__
        assert attributes[code_attributes.CODE_FUNCTION_NAME] == "test_a_record_reaches_the_exporter_with_the_fields_and_the_context_as_attributes"
        assert attributes[code_attributes.CODE_LINE_NUMBER] > 0

    def test_structured_content_rides_as_json_text_in_the_data_attribute(self, otlp_log: tuple[Log, InMemoryLogExporter]) -> None:
        fresh, exporter = otlp_log
        fresh.info({"key": "value", "nested": {"flag": True}}, title="Config")

        (log_data,) = _own_logs(exporter)
        assert _attributes(log_data)["data"] == '{"key": "value", "nested": {"flag": true}}'

    def test_the_exception_lands_under_the_semantic_convention_keys(self, otlp_log: tuple[Log, InMemoryLogExporter]) -> None:
        fresh, exporter = otlp_log
        try:
            msg = "boom"
            raise ValueError(msg)
        except ValueError:
            fresh.error("failed", include_exception=True)

        (log_data,) = _own_logs(exporter)
        assert log_data.log_record.body == "failed"
        assert log_data.log_record.severity_number is SeverityNumber.ERROR
        attributes = _attributes(log_data)
        assert attributes[exception_attributes.EXCEPTION_TYPE] == "ValueError"
        assert attributes[exception_attributes.EXCEPTION_MESSAGE] == "boom"
        assert "Traceback (most recent call last)" in attributes[exception_attributes.EXCEPTION_STACKTRACE]

    @pytest.mark.parametrize(
        ("method_name", "severity_text", "severity_number"),
        [
            ("verbose", "VERBOSE", SeverityNumber.TRACE),
            ("debug", "DEBUG", SeverityNumber.DEBUG),
            ("dev", "DEV", SeverityNumber.DEBUG4),
            ("info", "INFO", SeverityNumber.INFO),
            ("warning", "WARN", SeverityNumber.WARN),
            ("error", "ERROR", SeverityNumber.ERROR),
            ("critical", "CRITICAL", SeverityNumber.FATAL),
        ],
    )
    def test_every_level_maps_onto_the_otel_severity_scale(
        self,
        otlp_log: tuple[Log, InMemoryLogExporter],
        caplog: pytest.LogCaptureFixture,
        method_name: str,
        severity_text: str,
        severity_number: SeverityNumber,
    ) -> None:
        fresh, exporter = otlp_log
        caplog.set_level(logging.NOTSET + 1, logger=__name__)
        getattr(fresh, method_name)("at every level")

        (log_data,) = _own_logs(exporter)
        assert log_data.log_record.severity_text == severity_text
        assert log_data.log_record.severity_number is severity_number

    def test_a_record_from_the_opentelemetry_sdk_itself_is_not_exported(self, otlp_log: tuple[Log, InMemoryLogExporter]) -> None:
        """An exporter's own failure line must not re-enter the pipeline that failed."""
        _, exporter = otlp_log
        logging.getLogger("opentelemetry.exporter.otlp").error("Failed to export logs batch")
        logging.getLogger("opentelemetry").warning("dropped")

        scopes = {log_data.instrumentation_scope.name for log_data in exporter.get_finished_logs()}
        assert not any(scope == "opentelemetry" or scope.startswith("opentelemetry.") for scope in scopes)

    def test_the_sdks_own_record_is_rejected_before_the_handler_lock_is_taken(self, otlp_log: tuple[Log, InMemoryLogExporter]) -> None:
        """At exit the stdlib's shutdown holds this lock while it flushes, and an exporting thread reporting its failure must not wait on it."""
        fresh, _ = otlp_log
        assert fresh.sink is not None
        handler = fresh.sink.handler
        assert any(isinstance(handler_filter, ExportPathFilter) for handler_filter in handler.filters)
        sdk_record = logging.LogRecord(
            name="opentelemetry.sdk", level=logging.ERROR, pathname="", lineno=0, msg="export failed", args=(), exc_info=None
        )
        lock_taken = threading.Event()
        let_go = threading.Event()

        def hold_the_lock() -> None:
            handler.acquire()
            lock_taken.set()
            let_go.wait()
            handler.release()

        holder = threading.Thread(target=hold_the_lock)
        holder.start()
        lock_taken.wait()
        handled = threading.Event()

        def handle_the_sdks_record() -> None:
            handler.handle(sdk_record)
            handled.set()

        try:
            threading.Thread(target=handle_the_sdks_record, daemon=True).start()
            assert handled.wait(timeout=2), "the guard ran after the lock was taken"
        finally:
            let_go.set()
            holder.join()

    def test_a_record_emitted_during_an_export_is_rejected_whatever_its_logger_is_called(self, otlp_log: tuple[Log, InMemoryLogExporter]) -> None:
        """The SDK sets a context value around ``exporter.export``; the transport logs under it, and the sink reads it. A private key, pinned here."""
        fresh, exporter = otlp_log
        token = attach(set_value(_SUPPRESS_INSTRUMENTATION_KEY, True))
        try:
            logging.getLogger("urllib3.connectionpool").warning("Retrying after connection broken")
            fresh.info("mine, during an export")
        finally:
            detach(token)
        fresh.info("mine, after the export")

        assert [
            log_data.log_record.body for log_data in exporter.get_finished_logs() if log_data.instrumentation_scope.name.startswith("urllib3")
        ] == []
        assert [log_data.log_record.body for log_data in _own_logs(exporter)] == ["mine, after the export"]

    def test_a_mixed_type_sequence_rides_as_json_text_rather_than_being_dropped(self, otlp_log: tuple[Log, InMemoryLogExporter]) -> None:
        """The SDK keeps a sequence of one scalar type, compared by type equality, and drops the rest to ``None``."""
        fresh, exporter = otlp_log
        fresh.info("sequences", fields={"mixed": [1, "foo"], "int_bool": [1, True], "homogeneous": ["a", "b"], "empty": []})

        (log_data,) = _own_logs(exporter)
        attributes = _attributes(log_data)
        assert attributes["mixed"] == '[1, "foo"]'
        assert attributes["int_bool"] == "[1, true]"
        assert list(attributes["homogeneous"]) == ["a", "b"]
        assert list(attributes["empty"]) == []

    def test_flush_hands_the_provider_a_deadline(self, otlp_log: tuple[Log, InMemoryLogExporter], mocker: MockerFixture) -> None:
        fresh, _ = otlp_log
        sink = fresh.sink
        assert isinstance(sink, OtlpLogSink)
        force_flush = mocker.patch.object(sink.logger_provider, "force_flush")

        sink.handler.flush()

        force_flush.assert_called_once_with(timeout_millis=FLUSH_TIMEOUT_MILLIS)
