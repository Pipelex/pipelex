"""Protocol for trace event storage backends.

Defines the interface that all event log implementations must satisfy, and the one rule by which every one of them
returns the events of a run (`deduplicate_and_order_events`): the in-memory, NDJSON, DynamoDB and buffering logs.
"""

from collections.abc import Iterable
from typing import Protocol

from pipelex.tracing.trace_events import TraceEvent


def deduplicate_and_order_events(*, events: Iterable[TraceEvent]) -> list[TraceEvent]:
    """The events of a run as an event log returns them, whatever order its store holds them in.

    One event is kept per `TraceEvent.store_key` (chain, writer_id, event type, sequence), the first one met: a replay
    writes an event again under the same key, and a store may hold the same event under two keys of its own, such as
    a DynamoDB row written before its sort key changed shape. The events are ordered by (chain, sequence, writer_id):
    a dispatching attempt's events before those of the workflows it dispatched, whose chains continue its own, and,
    within one attempt, by sequence before writer, so that two writers emitting into the same attempt are not reordered
    by the lexical order of their ids.

    Args:
        events: The events read from the store, in any order, repeats included.

    Returns:
        The distinct events, ordered.
    """
    kept: dict[tuple[str, str, str, int], TraceEvent] = {}
    for event in events:
        kept.setdefault(event.store_key, event)
    return sorted(kept.values(), key=lambda event: (event.chain_key, event.sequence, event.writer_id))


class EventLogProtocol(Protocol):
    """Storage backend for trace events.

    Implementations must guarantee that emit() is synchronous and durable:
    when emit() returns, the event must be persisted. This invariant ensures
    all events from a child workflow are flushed before it returns to its parent.

    Each event log instance carries an immutable `writer_id` that emitters
    stamp on every TraceEvent they construct via this log. Two writers
    sharing the same (pipeline_run_id, workflow_id) partition must use
    distinct writer_ids so the read-side dedup key, `TraceEvent.store_key`
    (chain, writer_id, type, sequence), keeps their events apart.

    The chain, an event's lineage followed by its own workflow and attempt, is
    in the key so that a workflow's new attempt, which restarts its sequence,
    never overwrites the events of its earlier one, and neither does a workflow
    that a new attempt dispatched again under the same name.
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
        events of one attempt never collide on the (chain, writer_id, sequence)
        key regardless of storage backend.

        Implementations MUST be safe to call from multiple threads
        concurrently — the runner-side activity event log is cached
        per-process and shared by every activity thread on the worker, so
        unguarded reads/writes of the underlying counter would cause
        duplicate sequence numbers and silent dedup-key collisions.
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

        Returns events deduplicated by `TraceEvent.store_key` (chain, writer_id,
        event type, sequence) and sorted by (chain, sequence, writer_id) for
        deterministic ordering: a dispatching attempt's events before those of
        the workflows it dispatched, whose chains continue its own. Every
        implementation applies `deduplicate_and_order_events` to what its store
        holds, so none returns its store's own order.
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
