"""Temporal activity for flushing buffered trace events to the configured backend.

Called from wf_pipe_router after pipe execution to persist trace events
that were collected in-memory by BufferingEventLog during the workflow.
"""

from pydantic import BaseModel, Field
from temporalio import activity

from pipelex import log
from pipelex.config import get_config
from pipelex.temporal.tprl.activity_error_boundary import convert_pipelex_errors
from pipelex.tools.typing.pydantic_utils import empty_list_factory_of
from pipelex.tracing.event_log_factory import make_event_log
from pipelex.tracing.trace_events import TraceEvent


class FlushTraceEventsArg(BaseModel):
    """Input for the act_flush_trace_events activity."""

    events: list[TraceEvent] = Field(default_factory=empty_list_factory_of(TraceEvent))


@activity.defn(name="act_flush_trace_events")
@convert_pipelex_errors
async def act_flush_trace_events(arg: FlushTraceEventsArg) -> None:  # noqa: RUF029
    """Write buffered trace events to the configured backend. Runs as a Temporal
    activity so synchronous I/O (boto3, file writes) doesn't block the workflow thread.
    """
    if not arg.events:
        return

    tracing_config = get_config().pipelex.tracing_config
    if not tracing_config.is_enabled:
        return

    event_log = make_event_log(tracing_config)
    try:
        for event in arg.events:
            event_log.emit(event)
        log.debug(f"Flushed {len(arg.events)} trace events to backend={tracing_config.backend}")
    finally:
        event_log.close()
