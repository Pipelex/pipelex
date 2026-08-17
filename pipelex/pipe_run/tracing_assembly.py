"""Shared tracing-assembly logic for PipeRun implementations.

After pipe execution, reads the trace-event stream once and assembles both the
full GraphSpec (for ``--graph``) and the aggregated token usage (for ``--costs``)
from it. Works with any event log backend (NDJSON, DynamoDB, etc.) — the backend
is determined by the tracing config, not by the caller.

The same artifacts ride back on :class:`pipelex.core.pipes.pipe_output.PipeOutput`
in both DIRECT and TEMPORAL modes; :class:`TracingAssembly` is the small carrier
that crosses the Temporal activity boundary (returned by ``act_assemble_tracing``).
"""

import json

from pydantic import BaseModel, ConfigDict, ValidationError

from pipelex import log
from pipelex.base_exceptions import PipelexConfigError
from pipelex.config import get_config
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.graph.graphspec import GraphSpec, PipelineRef
from pipelex.reporting.reporting_types import AnyTokensUsage
from pipelex.runtime_hub import get_event_log_override
from pipelex.system.exceptions import MissingDependencyError
from pipelex.system.pipe_run_mode import PipeRunMode
from pipelex.tracing.event_log_factory import make_event_log
from pipelex.tracing.exceptions import EventLogError
from pipelex.tracing.graphspec_assembler import GraphSpecAssembler
from pipelex.tracing.usage_aggregator import UsageAggregator


class TracingAssembly(BaseModel):
    """Artifacts assembled from a single read of the trace-event stream.

    Mirrors the tracing fields on :class:`PipeOutput`. ``graph_spec`` /
    ``tokens_usages`` are populated only for the concerns that were requested and
    succeeded; the ``*_error`` fields carry a best-effort failure note otherwise.
    Returned by both the DIRECT assembly helper and the Temporal
    ``act_assemble_tracing`` activity, so it must stay serializable across the
    Temporal boundary (it is — ``AnyTokensUsage`` already crosses it via
    ``UsageReportEvent``).
    """

    model_config = ConfigDict(extra="forbid")

    graph_spec: GraphSpec | None = None
    graph_assembly_error: str | None = None
    tokens_usages: list[AnyTokensUsage] | None = None
    usage_assembly_error: str | None = None


def assemble_tracing(
    pipeline_run_id: str,
    *,
    assemble_graph: bool,
    assemble_usage: bool,
    domain_code: str | None = None,
    main_pipe_code: str | None = None,
    run_mode: PipeRunMode = PipeRunMode.LIVE,
) -> TracingAssembly:
    """Read the trace events for ``pipeline_run_id`` once and assemble the requested artifacts.

    Feeds the single event read into ``GraphSpecAssembler`` (when ``assemble_graph``)
    and ``UsageAggregator`` (when ``assemble_usage``).

    Tracing is observability and treated as best-effort: runtime I/O issues (the
    DynamoDB backend converts its botocore throttle / auth / transport / timeout
    failures into ``EventLogReadError`` on read and ``EventLogSetupError`` on client
    construction — both subclasses of ``EventLogError``; NDJSON read failures surface
    as ``OSError`` / ``JSONDecodeError``), malformed event data, and broken tracing
    infrastructure (config errors, missing optional dependencies) are caught and
    recorded in the ``*_error`` fields, not propagated. Programming bugs (KeyError,
    AttributeError, etc.) propagate so they surface during development.

    Args:
        pipeline_run_id: The pipeline run ID to query events for.
        assemble_graph: Whether to assemble a GraphSpec from the events.
        assemble_usage: Whether to aggregate token usage from the events.
        domain_code: Domain code for the graph's pipeline ref.
        main_pipe_code: Main pipe code for the graph's pipeline ref.
        run_mode: Final pipe run mode used to stamp GraphSpec provenance.

    Returns:
        A TracingAssembly carrying whichever artifacts were requested and succeeded.
    """
    result = TracingAssembly()
    tracing_config = get_config().runtime.tracing
    # A scoped override (see hub.scoped_event_log) is the run's transport and implies
    # tracing-enabled (D1) — it must not be skipped by the is_enabled early-return.
    event_log_override = get_event_log_override()
    if event_log_override is None and not tracing_config.is_enabled:
        return result
    if not (assemble_graph or assemble_usage):
        return result

    # Best-effort: a backend failure degrades to an *_assembly_error note rather than failing the run.
    # The DynamoDB backend converts its botocore failures (ClientError / BotoCoreError) into our
    # EventLogError family — EventLogSetupError on client construction (make_event_log), EventLogReadError
    # inside ``DynamoDBEventLog.read_events`` — so the assembly layer catches the EventLogError base and
    # never imports boto3 itself; NDJSON read failures surface as OSError / JSONDecodeError.
    try:
        if event_log_override is not None:
            # The scope owner keeps the instance's lifecycle: read without close().
            events = event_log_override.read_events(pipeline_run_id)
        else:
            event_log = make_event_log(tracing_config)
            try:
                events = event_log.read_events(pipeline_run_id)
            finally:
                event_log.close()
    except (OSError, json.JSONDecodeError, ValidationError, PipelexConfigError, MissingDependencyError, EventLogError) as read_error:
        message = f"Tracing assembly failed to read events for pipeline_run_id={pipeline_run_id}: {read_error}"
        log.warning(message)
        if assemble_graph:
            result.graph_assembly_error = message
        if assemble_usage:
            result.usage_assembly_error = message
        return result

    if not events:
        return result

    if assemble_usage:
        result.tokens_usages = UsageAggregator.aggregate(events)

    if assemble_graph:
        try:
            result.graph_spec = GraphSpecAssembler.assemble(
                events=events,
                graph_id=pipeline_run_id,
                pipeline_ref=PipelineRef(
                    domain=domain_code,
                    main_pipe=main_pipe_code,
                ),
                mode=run_mode.graphspec_mode,
            )
            log.debug(f"Graph assembled from {len(events)} events for pipeline_run_id={pipeline_run_id}")
        except ValidationError as validation_error:
            message = f"Graph assembly failed for pipeline_run_id={pipeline_run_id}: {validation_error}"
            log.warning(message)
            result.graph_assembly_error = message

    return result


def assemble_tracing_on_output(
    pipe_output: PipeOutput,
    *,
    pipeline_run_id: str,
    assemble_graph: bool,
    assemble_usage: bool,
    domain_code: str | None = None,
    main_pipe_code: str | None = None,
    run_mode: PipeRunMode = PipeRunMode.LIVE,
) -> None:
    """Assemble graph and/or usage from trace events and set them on pipe_output (DIRECT mode).

    Thin wrapper over :func:`assemble_tracing` that applies the assembled artifacts onto the
    PipeOutput. Only sets a field when its artifact was produced, so existing values are left
    untouched on a no-op / failed read.

    Args:
        pipe_output: The pipe output to set graph_spec / tokens_usages on.
        pipeline_run_id: The pipeline run ID to query events for.
        assemble_graph: Whether to assemble and set the GraphSpec.
        assemble_usage: Whether to aggregate and set token usage.
        domain_code: Domain code for the graph's pipeline ref.
        main_pipe_code: Main pipe code for the graph's pipeline ref.
        run_mode: Final pipe run mode used to stamp GraphSpec provenance.
    """
    result = assemble_tracing(
        pipeline_run_id=pipeline_run_id,
        assemble_graph=assemble_graph,
        assemble_usage=assemble_usage,
        domain_code=domain_code,
        main_pipe_code=main_pipe_code,
        run_mode=run_mode,
    )
    if result.graph_spec is not None:
        pipe_output.graph_spec = result.graph_spec
    if result.graph_assembly_error is not None:
        pipe_output.graph_assembly_error = result.graph_assembly_error
    if result.tokens_usages is not None:
        pipe_output.tokens_usages = result.tokens_usages
    if result.usage_assembly_error is not None:
        pipe_output.usage_assembly_error = result.usage_assembly_error
