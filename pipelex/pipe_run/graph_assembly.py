"""Shared graph assembly logic for PipeRun implementations.

After pipe execution, assembles the full GraphSpec from trace events.
Works with any event log backend (NDJSON, DynamoDB, etc.) — the backend
is determined by the tracing config, not by the caller.
"""

import json

from pydantic import ValidationError

from pipelex import log
from pipelex.base_exceptions import PipelexConfigError
from pipelex.config import get_config
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.graph.graphspec import PipelineRef
from pipelex.system.exceptions import MissingDependencyError
from pipelex.tracing.event_log_factory import make_event_log
from pipelex.tracing.exceptions import EventLogReadError
from pipelex.tracing.graphspec_assembler import GraphSpecAssembler


def assemble_graph_on_output(
    pipe_output: PipeOutput,
    pipeline_run_id: str,
    domain_code: str | None = None,
    main_pipe_code: str | None = None,
) -> None:
    """Assemble the full graph from trace events and set it on pipe_output.

    Reads all events for the pipeline_run_id from the configured event log
    backend and uses GraphSpecAssembler to build the complete cross-worker graph.
    Falls back to whatever graph_spec is already on pipe_output if assembly fails.

    Tracing is observability and treated as best-effort: runtime I/O issues,
    malformed event data, and broken tracing infrastructure (config errors,
    missing optional dependencies) are caught and warned about, not propagated.
    Programming bugs (KeyError, AttributeError, etc.) propagate so they surface
    during development.

    Args:
        pipe_output: The pipe output to set graph_spec on.
        pipeline_run_id: The pipeline run ID to query events for.
        domain_code: Domain code for the pipeline ref.
        main_pipe_code: Main pipe code for the pipeline ref.
    """
    tracing_config = get_config().pipelex.tracing_config
    if not tracing_config.is_enabled:
        return

    try:
        event_log = make_event_log(tracing_config)
        try:
            events = event_log.read_events(pipeline_run_id)
            if events:
                pipe_output.graph_spec = GraphSpecAssembler.assemble(
                    events=events,
                    graph_id=pipeline_run_id,
                    pipeline_ref=PipelineRef(
                        domain=domain_code,
                        main_pipe=main_pipe_code,
                    ),
                )
                log.debug(f"Graph assembled from {len(events)} events for pipeline_run_id={pipeline_run_id}")
        finally:
            event_log.close()
    except (OSError, json.JSONDecodeError, ValidationError, PipelexConfigError, MissingDependencyError, EventLogReadError) as graph_assembly_error:
        log.warning(f"Graph assembly failed, using existing graph: {graph_assembly_error}")
