"""What the ``gcp`` sink assumes of ``google-cloud-logging``, asserted against the installed library.

The sink declares the transport's shape rather than importing it, it computes the severity itself
rather than letting the library derive one from the level, because the library's own normalization has
no spelling for our ``VERBOSE``, and it rejects the library's own export path by the logger
names and the thread name the library chooses. Every one of those is an assumption about a third party
whose change would break a production sink silently and no other test would see: a renamed worker
thread or a renamed transport logger would let a refused batch be reported through the pipeline that
refused it, which is a spin that never ends and a deadlock at exit. The sink also refreshes, at boot,
the credentials the client keeps on a private attribute: renamed, the boot would fail on every process.
"""

from __future__ import annotations

import logging
from typing import Any, cast

from google.auth.credentials import AnonymousCredentials
from google.cloud import logging as cloud_logging
from google.cloud.logging_v2.entries import StructEntry
from google.cloud.logging_v2.handlers.transports.background_thread import (
    _WORKER_THREAD_NAME,  # pyright: ignore[reportPrivateUsage]
    _Worker,  # pyright: ignore[reportPrivateUsage]
)
from google.cloud.logging_v2.handlers.transports.base import Transport
from google.cloud.logging_v2.logger import Batch

from pipelex.tools.log.gcp_log_sink import (
    GCP_LOGGING_LOGGER_PREFIXES,
    GCP_WORKER_THREAD_NAME,
    MESSAGE_KEY,
    GcpLogSeverity,
    trace_name,
)


class TestTheClientLibraryContract:
    def test_the_transport_still_carries_the_three_methods_the_sink_calls(self) -> None:
        for method_name in ("send", "flush", "close"):
            assert callable(getattr(Transport, method_name))

    def test_the_severity_the_sink_passes_overrides_the_one_the_library_derives_from_the_level(self) -> None:
        # The worker only holds the logger for its own thread, which is never started here, so the
        # queued entry can be read without a client.
        worker: Any = _Worker(object())
        record = logging.LogRecord(name="pipelex", level=5, pathname="", lineno=0, msg="verbose line", args=(), exc_info=None)
        worker.enqueue(record, {MESSAGE_KEY: "verbose line"}, severity=GcpLogSeverity.DEBUG.value, labels={}, trace=None)

        queued = cast("dict[str, Any]", worker._queue.get_nowait())  # ruff: ignore[private-member-access]
        assert queued["severity"] == GcpLogSeverity.DEBUG.value
        assert queued["message"] == {MESSAGE_KEY: "verbose line"}
        assert queued["labels"]["python_logger"] == "pipelex"

    def test_a_struct_entry_renders_the_severity_name_and_the_trace_the_sink_passes(self) -> None:
        entry_trace = trace_name(project="p", trace_id=0xAB)
        # The library builds its entries from a namedtuple whose fields mypy does not see.
        entry: Any = StructEntry(payload={MESSAGE_KEY: "m"}, severity=GcpLogSeverity.WARNING.value, trace=entry_trace)  # type: ignore[call-arg]

        api_repr = cast("dict[str, Any]", entry.to_api_repr())
        assert api_repr["severity"] == GcpLogSeverity.WARNING.value
        assert api_repr["trace"] == entry_trace

    def test_the_trace_the_span_and_the_sampled_bit_the_sink_passes_reach_the_entry_through_the_queue(self) -> None:
        """The path the transport really takes: ``send`` enqueues the keyword arguments, and the batch builds the entry from them."""
        entry_trace = trace_name(project="p", trace_id=0xAB)
        worker: Any = _Worker(object())
        record = logging.LogRecord(name="pipelex", level=logging.INFO, pathname="", lineno=0, msg="m", args=(), exc_info=None)
        worker.enqueue(record, {MESSAGE_KEY: "m"}, labels={}, trace=entry_trace, span_id="00000000000000cd", trace_sampled=False)
        queued = cast("dict[str, Any]", worker._queue.get_nowait())  # ruff: ignore[private-member-access]
        # The library's batch is untyped; it is the one the worker builds its entries in.
        batch: Any = Batch(logger=None, client=None)
        batch.log(**queued)

        (entry,) = cast("list[Any]", batch.entries)
        api_repr = cast("dict[str, Any]", entry.to_api_repr())
        assert api_repr["trace"] == entry_trace
        assert api_repr["spanId"] == "00000000000000cd"
        assert api_repr["traceSampled"] is False

    def test_the_export_thread_still_carries_the_name_the_sinks_guard_rejects(self) -> None:
        assert GCP_WORKER_THREAD_NAME == _WORKER_THREAD_NAME

    def test_the_transport_reports_a_refused_batch_under_a_logger_the_guard_rejects(self) -> None:
        """The report the loop is made of: an ``ERROR`` on the library's own logger, propagating to the root."""
        transport_logger = logging.getLogger("google.cloud.logging_v2.handlers.transports.background_thread")
        assert any(transport_logger.name == prefix or transport_logger.name.startswith(f"{prefix}.") for prefix in GCP_LOGGING_LOGGER_PREFIXES)
        assert transport_logger.propagate
        assert transport_logger.isEnabledFor(logging.ERROR)

    def test_the_client_keeps_the_credentials_it_authenticates_with_where_the_sink_refreshes_them(self) -> None:
        credentials = AnonymousCredentials()
        client: Any = cloud_logging.Client(project="p", credentials=credentials)

        assert client._credentials is credentials  # ruff: ignore[private-member-access]
