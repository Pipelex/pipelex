"""In-memory event log implementation for unit tests and direct mode."""

from typing_extensions import override

from pipelex.tracing.event_log_protocol import EventLogProtocol
from pipelex.tracing.trace_events import TraceEvent


class InMemoryEventLog(EventLogProtocol):
    """Event log that stores events in a plain list.

    Useful for unit tests and optional use in direct mode (single-process).
    Provides the same deduplication and ordering guarantees as NdjsonEventLog.
    """

    def __init__(self) -> None:
        self._events: list[TraceEvent] = []

    @override
    def emit(self, event: TraceEvent) -> None:
        """Append event to the in-memory list."""
        self._events.append(event)

    @override
    def read_events(self, pipeline_run_id: str) -> list[TraceEvent]:
        """Return events for a pipeline run, deduplicated and sorted.

        Deduplicates by (workflow_id, sequence), keeping the first occurrence.
        Sorts by (workflow_id, sequence) for deterministic ordering.
        """
        filtered = [evt for evt in self._events if evt.pipeline_run_id == pipeline_run_id]

        seen: set[tuple[str, str, int]] = set()
        deduped: list[TraceEvent] = []
        for event in filtered:
            dedup_key = (event.workflow_id, type(event).__name__, event.sequence)
            if dedup_key not in seen:
                seen.add(dedup_key)
                deduped.append(event)

        deduped.sort(key=lambda evt: (evt.workflow_id, evt.sequence))
        return deduped

    @override
    def close(self) -> None:
        """No-op for in-memory implementation."""

    @override
    def cleanup(self, pipeline_run_id: str) -> None:
        """Remove all events for the given pipeline run."""
        self._events = [evt for evt in self._events if evt.pipeline_run_id != pipeline_run_id]
