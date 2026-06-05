"""Framework-agnostic graph assembly from buffered trace events.

Reads the configured trace-event backend (e.g. DynamoDB) and assembles the
GraphSpec for a completed pipeline run. Decoupled from any host-runtime
activity decorator so both ``pipelex.temporal`` and
``pipelex_mistralai_workflows`` can wrap it in their own activities.
"""

import json

from pydantic import ValidationError

from pipelex import log
from pipelex.base_exceptions import PipelexConfigError
from pipelex.config import get_config
from pipelex.graph.graphspec import GraphSpec, PipelineRef
from pipelex.system.exceptions import MissingDependencyError
from pipelex.tracing.event_log_factory import make_event_log
from pipelex.tracing.exceptions import EventLogReadError
from pipelex.tracing.graphspec_assembler import GraphSpecAssembler


async def assemble_graph_for_pipeline_run(  # noqa: RUF029
    pipeline_run_id: str,
    domain_code: str | None = None,
    main_pipe_code: str | None = None,
) -> GraphSpec | None:
    """Read trace events and assemble GraphSpec. Returns None if disabled or no events."""
    tracing_config = get_config().pipelex.tracing_config
    if not tracing_config.is_enabled:
        return None

    try:
        event_log = make_event_log(tracing_config)
        try:
            events = event_log.read_events(pipeline_run_id)
            if not events:
                log.debug(f"No trace events found for pipeline_run_id={pipeline_run_id}")
                return None
            graph_spec = GraphSpecAssembler.assemble(
                events=events,
                graph_id=pipeline_run_id,
                pipeline_ref=PipelineRef(
                    domain=domain_code,
                    main_pipe=main_pipe_code,
                ),
            )
            log.debug(f"Graph assembled from {len(events)} events for pipeline_run_id={pipeline_run_id}")
            return graph_spec
        finally:
            event_log.close()
    except (OSError, json.JSONDecodeError, ValidationError, PipelexConfigError, MissingDependencyError, EventLogReadError) as exc:
        # Best-effort observability: graph assembly must never fail the pipeline run. Expected
        # backend / parse / assembly failures degrade to None, which is why the host-runtime
        # activity wrapping this primitive is deliberately left undecorated by the error boundary.
        # Programming bugs (KeyError, AttributeError, ...) are NOT caught here so they surface
        # during development — this mirrors the in-process path in pipelex/pipe_run/graph_assembly.py.
        log.warning(f"Graph assembly failed: {exc}")
        return None
