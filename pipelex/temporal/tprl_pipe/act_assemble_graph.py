"""Temporal activity for assembling the graph spec from trace events.

Reads trace events from the configured backend (DynamoDB) and assembles
the full GraphSpec. Runs as an activity because DynamoDB reads are I/O
that cannot happen inside a workflow thread.
"""

from pydantic import BaseModel
from temporalio import activity

from pipelex import log
from pipelex.config import get_config
from pipelex.graph.graphspec import GraphSpec, PipelineRef
from pipelex.tracing.event_log_factory import make_event_log
from pipelex.tracing.graphspec_assembler import GraphSpecAssembler


class AssembleGraphArg(BaseModel):
    """Input for the graph assembly activity."""

    pipeline_run_id: str
    domain_code: str | None = None
    main_pipe_code: str | None = None


@activity.defn(name="act_assemble_graph")
async def act_assemble_graph(arg: AssembleGraphArg) -> GraphSpec | None:  # noqa: RUF029
    """Read trace events and assemble GraphSpec. Returns None if no events found."""
    tracing_config = get_config().pipelex.tracing_config
    if not tracing_config.is_enabled:
        return None

    try:
        event_log = make_event_log(tracing_config)
        try:
            events = event_log.read_events(arg.pipeline_run_id)
            if not events:
                log.debug(f"No trace events found for pipeline_run_id={arg.pipeline_run_id}")
                return None
            graph_spec = GraphSpecAssembler.assemble(
                events=events,
                graph_id=arg.pipeline_run_id,
                pipeline_ref=PipelineRef(
                    domain=arg.domain_code,
                    main_pipe=arg.main_pipe_code,
                ),
            )
            log.debug(f"Graph assembled from {len(events)} events for pipeline_run_id={arg.pipeline_run_id}")
            return graph_spec
        finally:
            event_log.close()
    except Exception as exc:
        # TODO: wip - do not catch all exceptions
        log.warning(f"Graph assembly activity failed: {exc}")
        return None
