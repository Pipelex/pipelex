"""In-memory buffering event log for use inside Temporal workflows.

Collects trace events in a list with zero I/O. Events are flushed to the
real backend (DynamoDB) via a Temporal activity after pipe execution.
"""

from typing_extensions import override

from pipelex.tracing.event_log_protocol import EventLogProtocol
from pipelex.tracing.trace_events import TraceEvent


class BufferingEventLog(EventLogProtocol):
    """Event log that buffers events in-memory for later flush via activity.

    Use inside Temporal workflows where synchronous I/O is forbidden.
    After pipe execution, call drain() to get the buffered events, then
    flush them to the real backend via act_flush_trace_events.
    """

    def __init__(self, writer_id: str = "primary") -> None:
        self._buffer: list[TraceEvent] = []
        self._sequence: int = 0
        self._writer_id = writer_id

    @property
    @override
    def writer_id(self) -> str:
        return self._writer_id

    @override
    def next_sequence(self) -> int:
        """Return the next sequence number. Shared by all emitters."""
        seq = self._sequence
        self._sequence += 1
        return seq

    @override
    def emit(self, event: TraceEvent) -> None:
        """Append event to in-memory buffer. No I/O."""
        self._buffer.append(event)

    def drain(self) -> list[TraceEvent]:
        """Return and clear all buffered events."""
        events = list(self._buffer)
        self._buffer.clear()
        return events

    @override
    def read_events(self, pipeline_run_id: str) -> list[TraceEvent]:
        """Return buffered events matching the pipeline_run_id."""
        return [event for event in self._buffer if event.pipeline_run_id == pipeline_run_id]

    @override
    def close(self) -> None:
        """No-op."""

    @override
    def cleanup(self, pipeline_run_id: str) -> None:
        """Remove buffered events for the given pipeline_run_id."""
        self._buffer = [event for event in self._buffer if event.pipeline_run_id != pipeline_run_id]
