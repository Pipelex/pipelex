"""Protocol for trace event storage backends.

Defines the interface that all event log implementations must satisfy.
The NDJSON backend is the local implementation; cloud backends (e.g. DynamoDB)
will implement the same protocol later.
"""

from typing import Protocol

from pipelex.tracing.trace_events import TraceEvent


class EventLogProtocol(Protocol):
    """Storage backend for trace events.

    Implementations must guarantee that emit() is synchronous and durable:
    when emit() returns, the event must be persisted. This invariant ensures
    all events from a child workflow are flushed before it returns to its parent.

    Each event log instance carries an immutable `writer_id` that emitters
    stamp on every TraceEvent they construct via this log. Two writers
    sharing the same (pipeline_run_id, workflow_id) partition must use
    distinct writer_ids so the read-side dedup key
    (workflow_id, writer_id, type, sequence) keeps their events apart.
    """

    @property
    def writer_id(self) -> str:
        """Stable identifier for this event log instance.

        Emitters read this to stamp every constructed TraceEvent. Defaults
        to "primary" for the legacy single-writer path so existing NDJSON
        files / DDB rows are not invalidated by code change.
        """
        ...

    def next_sequence(self) -> int:
        """Return the next monotonically increasing sequence number.

        All emitters sharing the same event log must use this method to
        obtain sequence numbers. Combined with writer_id, this guarantees
        events never collide on the (workflow_id, writer_id, sequence) key
        regardless of storage backend.
        """
        ...

    # TODO: wip - make it async
    def emit(self, event: TraceEvent) -> None:
        """Append a single event to the log.

        Must be synchronous with an explicit flush. The event is durable
        when this method returns.
        """
        ...

    # TODO: wip - make it async
    def read_events(self, pipeline_run_id: str) -> list[TraceEvent]:
        """Read all events for a pipeline run.

        Returns events deduplicated by (workflow_id, event_type, sequence) and sorted
        by (workflow_id, sequence) for deterministic ordering.
        Returns an empty list if no events exist for the given run.
        """
        ...

    def close(self) -> None:
        """Close all held resources (file handles, connections).

        Idempotent: safe to call multiple times. Does not delete data.
        """
        ...

    def cleanup(self, pipeline_run_id: str) -> None:
        """Remove all stored data for a pipeline run.

        Releases any held resources (file handles, connections) and deletes
        the underlying storage for the given run.
        """
        ...
