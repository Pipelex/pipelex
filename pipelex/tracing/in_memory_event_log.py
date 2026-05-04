"""In-memory event log implementation for unit tests and direct mode."""

import threading

from typing_extensions import override

from pipelex.tracing.event_log_protocol import EventLogProtocol
from pipelex.tracing.trace_events import TraceEvent


class InMemoryEventLog(EventLogProtocol):
    """Event log that stores events in a plain list.

    Useful for unit tests and optional use in direct mode (single-process).
    Provides the same deduplication and ordering guarantees as NdjsonEventLog.
    """

    def __init__(self, writer_id: str = "primary") -> None:
        self._events: list[TraceEvent] = []
        self._sequence: int = 0
        self._sequence_lock = threading.Lock()
        self._writer_id = writer_id

    @property
    @override
    def writer_id(self) -> str:
        return self._writer_id

    @override
    def next_sequence(self) -> int:
        """Return the next sequence number. Shared by all emitters.

        Guarded by a per-instance lock so concurrent emitters cannot
        collide on the dedup key.
        """
        with self._sequence_lock:
            seq = self._sequence
            self._sequence += 1
            return seq

    @override
    def emit(self, event: TraceEvent) -> None:
        """Append event to the in-memory list."""
        self._events.append(event)

    @override
    def read_events(self, pipeline_run_id: str) -> list[TraceEvent]:
        """Return events for a pipeline run, deduplicated and sorted.

        Deduplicates by (workflow_id, writer_id, type, sequence), keeping
        the first occurrence. Sorts by (workflow_id, sequence, writer_id) —
        sequence is primary so two writers emitting into the same workflow
        partition do not get reordered by writer-id lexicographic sort.
        """
        filtered = [evt for evt in self._events if evt.pipeline_run_id == pipeline_run_id]

        seen: set[tuple[str, str, str, int]] = set()
        deduped: list[TraceEvent] = []
        for event in filtered:
            dedup_key = (event.workflow_id, event.writer_id, type(event).__name__, event.sequence)
            if dedup_key not in seen:
                seen.add(dedup_key)
                deduped.append(event)

        deduped.sort(key=lambda evt: (evt.workflow_id, evt.sequence, evt.writer_id))
        return deduped

    @override
    def close(self) -> None:
        """No-op for in-memory implementation."""

    @override
    def cleanup(self, pipeline_run_id: str) -> None:
        """Remove all events for the given pipeline run."""
        self._events = [evt for evt in self._events if evt.pipeline_run_id != pipeline_run_id]
