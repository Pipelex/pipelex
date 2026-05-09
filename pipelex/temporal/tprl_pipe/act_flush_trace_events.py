"""Temporal activity wrapper for flushing buffered trace events.

Thin ``@activity.defn`` wrapper around the framework-agnostic core in
``pipelex.runtime_bridge.primitives.trace_flush``.
"""

from pydantic import BaseModel, Field
from temporalio import activity

from pipelex.runtime_bridge.primitives.trace_flush import flush_trace_events_to_backend
from pipelex.tools.typing.pydantic_utils import empty_list_factory_of
from pipelex.tracing.trace_events import TraceEvent


class FlushTraceEventsArg(BaseModel):
    """Input for the act_flush_trace_events activity."""

    events: list[TraceEvent] = Field(default_factory=empty_list_factory_of(TraceEvent))


@activity.defn(name="act_flush_trace_events")
async def act_flush_trace_events(arg: FlushTraceEventsArg) -> None:
    await flush_trace_events_to_backend(arg.events)
