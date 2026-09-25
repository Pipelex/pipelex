"""The ``gcp`` sink: a record reaches the Cloud Logging transport as one struct entry.

The sink is built around a fake transport, a subclass of the client library's own ``Transport``, so
each entry is captured where the library would have batched it; production builds it on the
``BackgroundThreadTransport`` around a real client instead. The guards on the export path are here
too, since what they guard is the handler. ``test_log_gcp_sink_mapping.py`` reads the severity scale
and the trace name on their own, ``test_log_gcp_json_payload_parity.py`` holds this payload and the
``json`` sink's line together, and ``test_log_gcp_client_library_contract.py`` pins what the sink
assumes of ``google-cloud-logging`` itself.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import TYPE_CHECKING, Any

import pytest
from google.cloud.logging_v2.handlers.transports.base import Transport
from typing_extensions import override

from pipelex.system.configuration.config_loader import ConfigLoader
from pipelex.tools.log.gcp_log_sink import (
    EXCEPTION_KEY,
    GCP_WORKER_THREAD_NAME,
    LOGGER_KEY,
    MESSAGE_KEY,
    GcpExportPathFilter,
    GcpLogSeverity,
    GcpLogSink,
)
from pipelex.tools.log.log import Log
from pipelex.tools.log.log_config import LogConfig
from pipelex.tools.log.log_redaction import CYCLE_TEXT
from pipelex.tools.misc.hash_utils import hash_md5_to_int
from pipelex.tools.misc.toml_utils import load_toml_from_path

if TYPE_CHECKING:
    from collections.abc import Iterator

    from pytest_mock import MockerFixture

PROJECT = "a-test-project"


class CapturedEntry:
    """One entry the sink handed the transport, as the transport received it."""

    def __init__(self, *, record: logging.LogRecord, payload: dict[str, Any], kwargs: dict[str, Any]) -> None:
        self.record = record
        self.payload = payload
        self.severity: Any = kwargs.get("severity")
        self.labels: dict[str, str] = kwargs.get("labels") or {}
        self.trace: str | None = kwargs.get("trace")


class FakeTransport(Transport):  # pyright: ignore[reportUntypedBaseClass]
    """The client library's transport contract, capturing instead of batching to the API."""

    def __init__(self) -> None:
        self.entries: list[CapturedEntry] = []
        self.flush_count = 0
        self.close_count = 0

    @override
    def send(self, record: logging.LogRecord, message: dict[str, Any], **kwargs: Any) -> None:  # kw-only: ignore — the library's own signature
        self.entries.append(CapturedEntry(record=record, payload=message, kwargs=kwargs))

    @override
    def flush(self) -> None:
        self.flush_count += 1

    @override
    def close(self) -> None:
        self.close_count += 1


def _package_log_config() -> LogConfig:
    config_dict = load_toml_from_path(ConfigLoader().pipelex_root_dir / "pipelex.toml")
    return LogConfig.model_validate(config_dict["runtime"]["log"])


def _own_entries(transport: FakeTransport) -> list[CapturedEntry]:
    """The entries this module's own records produced, whatever else the process logged meanwhile."""
    return [entry for entry in transport.entries if entry.record.name == __name__]


class NeverDrainingTransport(Transport):  # pyright: ignore[reportUntypedBaseClass]
    """A transport whose flush waits on a queue that never drains, which is what the library's does."""

    def __init__(self) -> None:
        self.entered = threading.Event()
        self.released = threading.Event()

    @override
    def send(self, record: logging.LogRecord, message: dict[str, Any], **kwargs: Any) -> None:  # kw-only: ignore — the library's own signature
        return None

    @override
    def flush(self) -> None:
        self.entered.set()
        # Bounded only so a regression fails the test instead of hanging the suite.
        self.released.wait(timeout=10)

    @override
    def close(self) -> None:
        return None


class FailingFlushTransport(Transport):  # pyright: ignore[reportUntypedBaseClass]
    """A transport whose flush raises, as one refusing the API does."""

    def __init__(self) -> None:
        self.message = "the API refused the batch"

    @override
    def send(self, record: logging.LogRecord, message: dict[str, Any], **kwargs: Any) -> None:  # kw-only: ignore — the library's own signature
        return None

    @override
    def flush(self) -> None:
        raise RuntimeError(self.message)

    @override
    def close(self) -> None:
        return None


class FailingCloseTransport(Transport):  # pyright: ignore[reportUntypedBaseClass]
    """A transport whose closing drain meets a refused batch, which the library reports through its own logger."""

    def __init__(self) -> None:
        self.handler: logging.Handler | None = None

    @override
    def send(self, record: logging.LogRecord, message: dict[str, Any], **kwargs: Any) -> None:  # kw-only: ignore — the library's own signature
        return None

    @override
    def flush(self) -> None:
        return None

    @override
    def close(self) -> None:
        assert self.handler is not None
        self.handler.handle(_library_record(level=logging.ERROR, msg="Failed to submit the last batch"))


class CapturingHandler(logging.Handler):
    """Stands in for the stdlib's last-resort handler, keeping what it would have printed on stderr."""

    def __init__(self) -> None:
        super().__init__(level=logging.WARNING)
        self.records: list[logging.LogRecord] = []

    @override
    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


class TestGcpLogSink:
    @pytest.fixture
    def gcp_log(self, caplog: pytest.LogCaptureFixture) -> Iterator[tuple[Log, FakeTransport]]:
        # pytest's ``log_level`` option restores the root logger's level at every phase boundary, undoing the
        # level ``configure`` sets from inside a fixture; the module's own logger is enabled explicitly and
        # ``caplog`` restores it at teardown.
        caplog.set_level(logging.INFO, logger=__name__)
        transport = FakeTransport()
        fresh = Log()
        fresh.configure(log_config=_package_log_config())
        fresh.install_sink(GcpLogSink(transport=transport, project=PROJECT))
        try:
            yield fresh, transport
        finally:
            fresh.reset()

    def test_the_message_and_the_fields_land_in_the_struct_payload(self, gcp_log: tuple[Log, FakeTransport]) -> None:
        fresh, transport = gcp_log
        fresh.info("scanned", fields={"files": 7, "ratio": 0.5, "tags": ["a", "b"], "meta": {"k": "v"}})

        (entry,) = _own_entries(transport)
        assert entry.payload[MESSAGE_KEY] == "scanned"
        assert entry.payload[LOGGER_KEY] == __name__
        assert entry.payload["files"] == 7
        assert entry.payload["ratio"] == 0.5
        assert entry.payload["tags"] == ["a", "b"]
        assert entry.payload["meta"] == {"k": "v"}
        assert entry.severity == GcpLogSeverity.INFO.value

    def test_the_run_scoped_identifiers_become_labels_and_stay_out_of_the_payload(self, gcp_log: tuple[Log, FakeTransport]) -> None:
        fresh, transport = gcp_log
        with fresh.context(request_id="r1", pipe_run_id="pr1"):
            fresh.info("bound")

        (entry,) = _own_entries(transport)
        assert entry.labels == {"request_id": "r1", "pipe_run_id": "pr1"}
        assert "request_id" not in entry.payload
        assert "pipe_run_id" not in entry.payload

    def test_the_trace_field_carries_the_runs_own_trace_id_project_qualified(self, gcp_log: tuple[Log, FakeTransport]) -> None:
        fresh, transport = gcp_log
        with fresh.context(pipeline_run_id="plr-01"):
            fresh.info("running")

        (entry,) = _own_entries(transport)
        assert entry.trace == f"projects/{PROJECT}/traces/{hash_md5_to_int('plr-01'):032x}"
        assert entry.labels == {"pipeline_run_id": "plr-01"}

    def test_a_record_outside_any_run_carries_no_trace_and_no_labels(self, gcp_log: tuple[Log, FakeTransport]) -> None:
        fresh, transport = gcp_log
        fresh.info("unbound")

        (entry,) = _own_entries(transport)
        assert entry.trace is None
        assert entry.labels == {}

    def test_structured_content_rides_in_the_data_key_of_the_payload(self, gcp_log: tuple[Log, FakeTransport]) -> None:
        fresh, transport = gcp_log
        fresh.info({"key": "value", "nested": {"flag": True}}, title="Config")

        (entry,) = _own_entries(transport)
        assert entry.payload["data"] == {"key": "value", "nested": {"flag": True}}

    def test_a_value_json_cannot_carry_is_written_as_text_rather_than_costing_the_line(self, gcp_log: tuple[Log, FakeTransport]) -> None:
        """A non-finite float is spelled as text, and a cycle is cut by the redaction walk and keeps the payload a struct."""
        fresh, transport = gcp_log
        circular: dict[str, Any] = {}
        circular["self"] = circular
        fresh.info("odd values", fields={"nan": float("nan"), "inf": float("inf"), "circular": circular})

        (entry,) = _own_entries(transport)
        assert entry.payload[MESSAGE_KEY] == "odd values"
        assert entry.payload["nan"] == "NaN"
        assert entry.payload["inf"] == "Infinity"
        assert entry.payload["circular"] == {"self": CYCLE_TEXT}

    def test_a_raw_cycle_reaching_the_handler_is_written_as_text_rather_than_costing_the_line(self) -> None:
        """The sink's own guard, for a process with redaction off: a value ``json`` refuses is written as its ``repr``, the payload stays a struct."""
        transport = FakeTransport()
        handler = GcpLogSink(transport=transport, project=PROJECT).make_handler()
        cyclic: dict[str, Any] = {}
        cyclic["me"] = cyclic
        record = logging.LogRecord(name=__name__, level=logging.INFO, pathname="", lineno=0, msg="cyclic value", args=(), exc_info=None)
        record.loop = cyclic

        handler.handle(record)

        (entry,) = transport.entries
        assert entry.payload[MESSAGE_KEY] == "cyclic value"
        assert isinstance(entry.payload["loop"], str)
        assert "{...}" in entry.payload["loop"]

    def test_a_field_named_like_a_fixed_key_keeps_its_value_under_the_prefix(self, gcp_log: tuple[Log, FakeTransport]) -> None:
        fresh, transport = gcp_log
        fresh.info("the message", fields={"logger": "mine"})

        (entry,) = _own_entries(transport)
        assert entry.payload[LOGGER_KEY] == __name__
        assert entry.payload["field_logger"] == "mine"

    def test_the_exception_lands_under_the_exception_key(self, gcp_log: tuple[Log, FakeTransport]) -> None:
        fresh, transport = gcp_log
        try:
            msg = "boom"
            raise ValueError(msg)
        except ValueError:
            fresh.error("failed", include_exception=True)

        (entry,) = _own_entries(transport)
        assert entry.severity == GcpLogSeverity.ERROR.value
        assert "Traceback (most recent call last)" in entry.payload[EXCEPTION_KEY]
        assert "ValueError: boom" in entry.payload[EXCEPTION_KEY]

    @pytest.mark.parametrize(
        ("method_name", "severity"),
        [
            ("verbose", GcpLogSeverity.DEBUG),
            ("debug", GcpLogSeverity.DEBUG),
            ("dev", GcpLogSeverity.DEBUG),
            ("info", GcpLogSeverity.INFO),
            ("warning", GcpLogSeverity.WARNING),
            ("error", GcpLogSeverity.ERROR),
            ("critical", GcpLogSeverity.CRITICAL),
        ],
    )
    def test_every_level_maps_onto_the_cloud_logging_severity_scale(
        self,
        gcp_log: tuple[Log, FakeTransport],
        caplog: pytest.LogCaptureFixture,
        method_name: str,
        severity: GcpLogSeverity,
    ) -> None:
        fresh, transport = gcp_log
        caplog.set_level(logging.NOTSET + 1, logger=__name__)
        getattr(fresh, method_name)("at every level")

        (entry,) = _own_entries(transport)
        assert entry.severity == severity.value

    def test_the_teardown_flushes_and_closes_the_transport(self, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level(logging.INFO, logger=__name__)
        transport = FakeTransport()
        fresh = Log()
        fresh.configure(log_config=_package_log_config())
        fresh.install_sink(GcpLogSink(transport=transport, project=PROJECT))
        fresh.reset()

        assert transport.flush_count > 0

    def test_the_client_librarys_own_export_failure_is_rejected_rather_than_exported(self, gcp_log: tuple[Log, FakeTransport]) -> None:
        """The library reports a refused batch at ``ERROR``; exported, that report fails with the batch and is reported again."""
        _, transport = gcp_log
        logging.getLogger("google.cloud.logging_v2.handlers.transports.background_thread").error("Failed to submit 1 logs.")
        logging.getLogger("google.cloud.logging").warning("dropped")

        assert [entry for entry in transport.entries if entry.record.name.startswith("google.cloud.logging")] == []

    def test_a_record_emitted_on_the_export_thread_is_rejected_whatever_its_logger_is_called(self, gcp_log: tuple[Log, FakeTransport]) -> None:
        """The auth stack and the HTTP client log under their own names, and only ever reach this handler from that thread."""
        _, transport = gcp_log

        def log_as_the_exporting_thread() -> None:
            logging.getLogger("urllib3.connectionpool").error("Retrying after connection broken")

        exporting = threading.Thread(target=log_as_the_exporting_thread, name=GCP_WORKER_THREAD_NAME)
        exporting.start()
        exporting.join()
        logging.getLogger("urllib3.connectionpool").error("Retrying, on any other thread")

        urllib3_entries = [entry for entry in transport.entries if entry.record.name.startswith("urllib3")]
        assert [entry.payload[MESSAGE_KEY] for entry in urllib3_entries] == ["Retrying, on any other thread"]

    def test_the_export_paths_record_is_rejected_before_the_handler_lock_is_taken(self, gcp_log: tuple[Log, FakeTransport]) -> None:
        """At exit the stdlib's shutdown holds this lock while it flushes, and an exporting thread reporting its failure must not wait on it."""
        fresh, _ = gcp_log
        assert fresh.sink is not None
        handler = fresh.sink.handler
        assert any(isinstance(handler_filter, GcpExportPathFilter) for handler_filter in handler.filters)
        library_record = logging.LogRecord(
            name="google.cloud.logging_v2.handlers.transports.background_thread",
            level=logging.ERROR,
            pathname="",
            lineno=0,
            msg="Failed to submit 1 logs.",
            args=(),
            exc_info=None,
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

        def handle_the_librarys_record() -> None:
            handler.handle(library_record)
            handled.set()

        try:
            threading.Thread(target=handle_the_librarys_record, daemon=True).start()
            assert handled.wait(timeout=2), "the guard ran after the lock was taken"
        finally:
            let_go.set()
            holder.join()

    def test_the_flush_gives_up_on_a_queue_that_never_drains(self, mocker: MockerFixture) -> None:
        """The library's flush ends in ``queue.join()``, which takes no deadline, so the teardown would never return."""
        mocker.patch("pipelex.tools.log.gcp_log_sink.FLUSH_TIMEOUT_SECONDS", 0.2)
        transport = NeverDrainingTransport()
        handler = GcpLogSink(transport=transport, project=PROJECT).make_handler()

        started = time.monotonic()
        try:
            handler.flush()
            waited = time.monotonic() - started
        finally:
            transport.released.set()

        assert transport.entered.is_set(), "the flush never reached the transport"
        assert waited < 5, f"the flush waited {waited:.1f}s on a queue that never drains"

    def test_a_transport_that_refuses_the_flush_still_reports_it(self) -> None:
        """The bound must not swallow what the teardown is there to report."""
        handler = GcpLogSink(transport=FailingFlushTransport(), project=PROJECT).make_handler()

        with pytest.raises(RuntimeError, match="the API refused the batch"):
            handler.flush()

    def test_an_export_failure_is_printed_on_stderr_rather_than_exported(self, gcp_log: tuple[Log, FakeTransport], mocker: MockerFixture) -> None:
        """The library reports a refused batch only through this record, and the sink's own handler is never the place it can go."""
        _, transport = gcp_log
        stderr = CapturingHandler()
        mocker.patch.object(logging, "lastResort", stderr)

        logging.getLogger("google.cloud.logging_v2.handlers.transports.background_thread").error("Failed to submit 10 logs.")

        assert [record.getMessage() for record in stderr.records] == ["Failed to submit 10 logs."]
        assert [entry for entry in transport.entries if entry.record.name.startswith("google.cloud.logging")] == []

    def test_the_export_paths_routine_records_are_not_printed(self, mocker: MockerFixture) -> None:
        stderr = CapturingHandler()
        mocker.patch.object(logging, "lastResort", stderr)
        export_filter = GcpExportPathFilter()

        assert not export_filter.filter(_library_record(level=logging.DEBUG, msg="Submitted 10 logs"))
        assert stderr.records == []

    def test_a_refusal_that_persists_is_counted_rather_than_printed_per_batch(self, mocker: MockerFixture) -> None:
        """One report per refused commit is one per line the application logs; the stderr it takes must not grow with that."""
        stderr = CapturingHandler()
        mocker.patch.object(logging, "lastResort", stderr)
        export_filter = GcpExportPathFilter(report_interval_seconds=0.5)

        for batch_number in range(3):
            export_filter.filter(_library_record(level=logging.ERROR, msg=f"Failed to submit batch {batch_number}"))
        assert [record.getMessage() for record in stderr.records] == ["Failed to submit batch 0"]

        time.sleep(0.6)
        export_filter.filter(_library_record(level=logging.ERROR, msg="Failed to submit batch 3"))
        assert [record.getMessage() for record in stderr.records] == [
            "Failed to submit batch 0",
            "The gcp log sink's transport reported 2 more export failures since the last one printed",
            "Failed to submit batch 3",
        ]

    def test_a_count_left_when_the_failures_stop_is_printed_once_its_window_has_passed(self, mocker: MockerFixture) -> None:
        """An outage that ends leaves its count behind, and no later failure comes to print it."""
        stderr = CapturingHandler()
        mocker.patch.object(logging, "lastResort", stderr)
        export_filter = GcpExportPathFilter(report_interval_seconds=0.5)

        for batch_number in range(3):
            export_filter.filter(_library_record(level=logging.ERROR, msg=f"Failed to submit batch {batch_number}"))
        assert export_filter.filter(_application_record())
        assert [record.getMessage() for record in stderr.records] == ["Failed to submit batch 0"]

        time.sleep(0.6)
        assert export_filter.filter(_application_record())
        assert [record.getMessage() for record in stderr.records] == [
            "Failed to submit batch 0",
            "The gcp log sink's transport reported 2 more export failures since the last one printed",
        ]

    def test_the_handler_prints_the_count_left_at_close_including_what_the_closing_drain_adds(self, mocker: MockerFixture) -> None:
        """The close drains the queue, and a refusal met there is counted inside a window nothing else would close."""
        stderr = CapturingHandler()
        mocker.patch.object(logging, "lastResort", stderr)
        transport = FailingCloseTransport()
        handler = GcpLogSink(transport=transport, project=PROJECT).make_handler()
        transport.handler = handler

        handler.handle(_library_record(level=logging.ERROR, msg="Failed to submit batch 0"))
        handler.close()

        assert [record.getMessage() for record in stderr.records] == [
            "Failed to submit batch 0",
            "The gcp log sink's transport reported 1 more export failures since the last one printed",
        ]


def _application_record() -> logging.LogRecord:
    """A record the application logs, which the filter passes."""
    return logging.LogRecord(name=__name__, level=logging.INFO, pathname="", lineno=0, msg="an ordinary line", args=(), exc_info=None)


def _library_record(*, level: int, msg: str) -> logging.LogRecord:
    """A record as the client library's transport logger emits it."""
    return logging.LogRecord(
        name="google.cloud.logging_v2.handlers.transports.background_thread", level=level, pathname="", lineno=0, msg=msg, args=(), exc_info=None
    )
