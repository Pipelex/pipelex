"""Concurrent sequence allocation must yield unique, contiguous values across threads."""

import sys
import threading
from collections.abc import Iterator
from typing import TYPE_CHECKING, Any

import pytest
from pytest_mock import MockerFixture

from pipelex.tracing.buffering_event_log import BufferingEventLog
from pipelex.tracing.dynamodb_event_log import DynamoDBEventLog
from pipelex.tracing.in_memory_event_log import InMemoryEventLog
from pipelex.tracing.ndjson_event_log import NdjsonEventLog

if TYPE_CHECKING:
    from pipelex.tracing.event_log_protocol import EventLogProtocol


@pytest.fixture
def aggressive_gil_switching() -> Iterator[None]:
    """Lower the GIL switch interval to force frequent thread interleaving.

    Without this, CPython batches many bytecodes between GIL releases and the
    `seq = self._sequence; self._sequence += 1` race effectively never triggers
    in short test runs. Restored after the test.
    """
    original_interval = sys.getswitchinterval()
    sys.setswitchinterval(1e-9)
    try:
        yield
    finally:
        sys.setswitchinterval(original_interval)


@pytest.mark.usefixtures("aggressive_gil_switching")
class TestEventLogSequenceThreadSafety:
    @pytest.mark.parametrize(
        "backend_name",
        ["ndjson", "in_memory", "buffering", "dynamodb"],
    )
    def test_concurrent_next_sequence_returns_unique_contiguous_values(
        self,
        backend_name: str,
        tmp_path: Any,
        mocker: MockerFixture,
    ) -> None:
        nb_threads = 16
        nb_calls = 2000
        total_calls = nb_threads * nb_calls

        event_log: EventLogProtocol
        match backend_name:
            case "ndjson":
                event_log = NdjsonEventLog(traces_dir=str(tmp_path))
            case "in_memory":
                event_log = InMemoryEventLog()
            case "buffering":
                event_log = BufferingEventLog()
            case "dynamodb":
                mocker.patch("pipelex.tracing.dynamodb_event_log.boto3")
                event_log = DynamoDBEventLog(table_name="t", region="us-east-1")
            case _:
                msg = f"Unknown backend_name: {backend_name}"
                raise ValueError(msg)

        results: list[int] = []
        results_lock = threading.Lock()
        barrier = threading.Barrier(nb_threads)

        def worker() -> None:
            barrier.wait()
            local: list[int] = [event_log.next_sequence() for _ in range(nb_calls)]
            with results_lock:
                results.extend(local)

        threads = [threading.Thread(target=worker) for _ in range(nb_threads)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert len(results) == total_calls
        assert len(set(results)) == total_calls, "next_sequence returned duplicate values under concurrency"
        assert set(results) == set(range(total_calls)), "next_sequence skipped or repeated values under concurrency"
