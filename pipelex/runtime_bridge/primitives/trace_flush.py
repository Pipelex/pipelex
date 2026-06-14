"""Framework-agnostic flush of buffered trace events to the configured backend.

Called from a host-runtime activity (Temporal / Mistral) after a workflow's
``BufferingEventLog`` has drained, since synchronous I/O (boto3, file
writes) cannot run inside a workflow thread.
"""

from pipelex import log
from pipelex.config import get_config
from pipelex.tracing.event_log_factory import make_event_log
from pipelex.tracing.trace_events import TraceEvent


async def flush_trace_events_to_backend(events: list[TraceEvent]) -> None:  # noqa: RUF029
    """Persist buffered trace events to the configured backend.

    No-op when the events list is empty or tracing is disabled.
    """
    if not events:
        return

    tracing_config = get_config().pipelex.tracing_config
    if not tracing_config.is_enabled:
        return

    event_log = make_event_log(tracing_config)
    try:
        for event in events:
            event_log.emit(event)
        log.debug(f"Flushed {len(events)} trace events to backend={tracing_config.backend}")
    finally:
        event_log.close()
