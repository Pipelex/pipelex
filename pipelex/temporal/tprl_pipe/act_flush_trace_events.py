"""Temporal activity for flushing buffered trace events to the configured backend.

Called from wf_pipe_router after pipe execution to persist trace events
that were collected in-memory by BufferingEventLog during the workflow.
"""

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field
from temporalio import activity

from pipelex import log
from pipelex.config import get_config
from pipelex.system.configuration.configs import TracingBackend
from pipelex.tools.typing.pydantic_utils import empty_list_factory_of
from pipelex.tracing.dynamodb_event_log import DynamoDBEventLog
from pipelex.tracing.ndjson_event_log import NdjsonEventLog
from pipelex.tracing.trace_events import TraceEvent

if TYPE_CHECKING:
    from pipelex.tracing.event_log_protocol import EventLogProtocol


class FlushTraceEventsArg(BaseModel):
    """Input for the act_flush_trace_events activity."""

    events: list[TraceEvent] = Field(default_factory=empty_list_factory_of(TraceEvent))


@activity.defn(name="act_flush_trace_events")
async def act_flush_trace_events(arg: FlushTraceEventsArg) -> None:  # noqa: RUF029
    """Write buffered trace events to the configured backend. Runs as a Temporal
    activity so synchronous I/O (boto3, file writes) doesn't block the workflow thread.
    """
    if not arg.events:
        return

    tracing_config = get_config().pipelex.tracing_config
    if not tracing_config.is_enabled:
        return

    event_log: EventLogProtocol
    match tracing_config.backend:
        case TracingBackend.TEMPORAL_DYNAMODB:
            if tracing_config.temporal_dynamodb is None:
                log.warning("temporal_dynamodb config missing, cannot flush trace events")
                return
            event_log = DynamoDBEventLog(
                table_name=tracing_config.temporal_dynamodb.table_name,
                region=tracing_config.temporal_dynamodb.region,
            )
        case TracingBackend.NDJSON:
            if tracing_config.ndjson is None:
                log.warning("ndjson config missing, cannot flush trace events")
                return
            event_log = NdjsonEventLog(traces_dir=tracing_config.ndjson.traces_dir)
        case TracingBackend.DYNAMODB:
            if tracing_config.dynamodb is None:
                log.warning("dynamodb config missing, cannot flush trace events")
                return
            event_log = DynamoDBEventLog(
                table_name=tracing_config.dynamodb.table_name,
                region=tracing_config.dynamodb.region,
            )

    try:
        for event in arg.events:
            event_log.emit(event)
        log.debug(f"Flushed {len(arg.events)} trace events to backend={tracing_config.backend}")
    finally:
        event_log.close()
