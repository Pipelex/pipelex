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
from typing import NamedTuple

from pydantic import BaseModel, ConfigDict, PrivateAttr, ValidationError

from pipelex import log
from pipelex.base_exceptions import PipelexConfigError
from pipelex.config import get_config
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.graph.graphspec import GraphSpec, PipelineRef
from pipelex.reporting.reporting_types import AnyTokensUsage
from pipelex.runtime_hub import get_event_log_override
from pipelex.system.exceptions import MissingDependencyError
from pipelex.system.job_metadata import RunMetadata
from pipelex.tools.log.error_fields import error_fields
from pipelex.tracing.event_log_factory import make_event_log
from pipelex.tracing.exceptions import EventLogError, TraceEventModeError
from pipelex.tracing.graphspec_assembler import GraphSpecAssembler
from pipelex.tracing.trace_events import TraceEvent
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

    # The run this assembly belongs to. Same purpose as `PipeOutput.job_metadata`
    # and, for the same reason, the same shape: a private attribute behind a
    # property rather than a model field, so it is readable by a transport
    # resolving a storage scope and absent from every serialization and schema.
    #
    # `RunMetadata` rather than the whole `JobMetadata`: an assembly belongs to the
    # RUN, not to any one job within it, and the per-job half would be a lie here.
    _run_metadata: RunMetadata | None = PrivateAttr(default=None)

    @property
    def run_metadata(self) -> RunMetadata | None:
        return self._run_metadata

    def set_run_metadata(self, *, run_metadata: RunMetadata | None) -> None:
        """Set the run_metadata a transport reads to place this result's bytes.

        A METHOD, not a `@run_metadata.setter`: this repo's keyword-only convention
        rewrites a positional setter parameter into a keyword-only one, which is not
        a valid property-setter signature. A named method takes the keyword happily
        and says what it does at the call site.
        """
        self._run_metadata = run_metadata


class RunTraceEvents(NamedTuple):
    """The one read of a run's trace events: what it returned, or why it returned nothing.

    ``events`` is ``None`` when the events were not read (tracing is off) or could not be; ``read_error`` says
    which, carrying the note the assembly records when the read failed.
    """

    events: list[TraceEvent] | None
    read_error: str | None

    @property
    def was_read(self) -> bool:
        return self.events is not None


def read_run_trace_events(*, pipeline_run_id: str) -> RunTraceEvents:
    """Read the trace events of ``pipeline_run_id`` once, from the run's scoped event log or the configured backend.

    Best-effort, for the reasons :func:`assemble_tracing` gives: a backend failure, malformed event data or broken
    tracing infrastructure returns no events and the failure's note, never raises. With tracing off and no scoped
    event log, nothing is read.
    """
    tracing_config = get_config().runtime.tracing
    # A scoped override (see hub.scoped_event_log) is the run's transport and implies
    # tracing-enabled (D1) — it must not be skipped by the is_enabled early-return.
    event_log_override = get_event_log_override()
    if event_log_override is None and not tracing_config.is_enabled:
        return RunTraceEvents(events=None, read_error=None)

    # Best-effort: a backend failure degrades to an *_assembly_error note rather than failing the run.
    # The DynamoDB backend converts its botocore failures (ClientError / BotoCoreError) into our
    # EventLogError family — EventLogSetupError on client construction (make_event_log), EventLogReadError
    # inside ``DynamoDBEventLog.read_events`` — so the assembly layer catches the EventLogError base and
    # never imports boto3 itself; NDJSON read failures surface as OSError. Both backends refuse a log holding an
    # event the current models do not accept with EventLogSchemaMismatchError, which drops the graph and the usage.
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
        log.warning("The trace events of a run could not be read for its tracing assembly", fields=error_fields(exc=read_error))
        return RunTraceEvents(
            events=None,
            read_error=f"Tracing assembly failed to read events for pipeline_run_id={pipeline_run_id}: {read_error}",
        )
    return RunTraceEvents(events=events, read_error=None)


def assemble_tracing(
    pipeline_run_id: str,
    *,
    assemble_graph: bool,
    assemble_usage: bool,
    domain_code: str | None = None,
    main_pipe_code: str | None = None,
    run_metadata: RunMetadata | None = None,
    trace_events: RunTraceEvents | None = None,
) -> TracingAssembly:
    """Read the trace events for ``pipeline_run_id`` once and assemble the requested artifacts.

    Feeds the single event read into ``GraphSpecAssembler`` (when ``assemble_graph``)
    and ``UsageAggregator`` (when ``assemble_usage``).

    Tracing is observability and treated as best-effort: runtime I/O issues (the
    DynamoDB backend converts its botocore throttle / auth / transport / timeout
    failures into ``EventLogReadError`` on read and ``EventLogSetupError`` on client
    construction — both subclasses of ``EventLogError``; NDJSON read failures surface
    as ``OSError``), malformed event data, and broken tracing infrastructure (config
    errors, missing optional dependencies) are caught and recorded in the ``*_error``
    fields, not propagated. Either backend refuses a log holding an event the current
    models do not accept with ``EventLogSchemaMismatchError``, also an ``EventLogError``:
    the read fails as a whole, so such a run gets neither its graph nor its usage total. The graph's provenance mode is
    the run mode its events state: events that mix modes hold more than one run, and get no graph, the assembler's
    ``TraceEventModeError`` recorded in ``graph_assembly_error``. Programming bugs (KeyError, AttributeError, etc.)
    propagate so they surface during development.

    Args:
        pipeline_run_id: The pipeline run ID to query events for.
        assemble_graph: Whether to assemble a GraphSpec from the events.
        assemble_usage: Whether to aggregate token usage from the events.
        domain_code: Domain code for the graph's pipeline ref.
        main_pipe_code: Main pipe code for the graph's pipeline ref.
        run_metadata: The run this assembly belongs to, stamped onto the result so a
            transport that offloads it keys it inside the run's namespace. None for a
            run with no host-supplied scope.
        trace_events: The run's events, already read by the caller for another reader of the same events (the run's
            usage statistics), so the run's events are still read once; None to read them here.

    Returns:
        A TracingAssembly carrying whichever artifacts were requested and succeeded.
    """
    result = TracingAssembly()
    result.set_run_metadata(run_metadata=run_metadata)
    # Bound here rather than left to the caller: besides `PipeRun`'s run, whose context binds the run already, this is
    # the body of the durable-execution activity `act_assemble_tracing`, which runs under no binding of the run, so its
    # lines would name no run. A `request_id` of `None` inherits whatever the caller bound.
    with log.context(request_id=run_metadata.request_id if run_metadata else None, pipeline_run_id=pipeline_run_id):
        return _assemble_tracing_events(
            result=result,
            pipeline_run_id=pipeline_run_id,
            assemble_graph=assemble_graph,
            assemble_usage=assemble_usage,
            domain_code=domain_code,
            main_pipe_code=main_pipe_code,
            trace_events=trace_events,
        )


def _assemble_tracing_events(
    *,
    result: TracingAssembly,
    pipeline_run_id: str,
    assemble_graph: bool,
    assemble_usage: bool,
    domain_code: str | None,
    main_pipe_code: str | None,
    trace_events: RunTraceEvents | None,
) -> TracingAssembly:
    """The body of ``assemble_tracing``, run inside the log context it binds: read the events once, assemble onto ``result``."""
    if not (assemble_graph or assemble_usage):
        return result

    if trace_events is None:
        trace_events = read_run_trace_events(pipeline_run_id=pipeline_run_id)
    if trace_events.read_error is not None:
        if assemble_graph:
            result.graph_assembly_error = trace_events.read_error
        if assemble_usage:
            result.usage_assembly_error = trace_events.read_error
        return result
    events = trace_events.events
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
            )
            log.debug("Assembled the graph from the trace events", fields={"event_count": len(events)})
        except (ValidationError, TraceEventModeError) as assembly_error:
            log.warning("The graph could not be assembled from the trace events", fields=error_fields(exc=assembly_error))
            result.graph_assembly_error = f"Graph assembly failed for pipeline_run_id={pipeline_run_id}: {assembly_error}"

    return result


def assemble_tracing_on_output(
    pipe_output: PipeOutput,
    *,
    pipeline_run_id: str,
    assemble_graph: bool,
    assemble_usage: bool,
    domain_code: str | None = None,
    main_pipe_code: str | None = None,
    trace_events: RunTraceEvents | None = None,
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
        trace_events: The run's events when the caller already read them; None to read them here.
    """
    result = assemble_tracing(
        pipeline_run_id=pipeline_run_id,
        assemble_graph=assemble_graph,
        assemble_usage=assemble_usage,
        domain_code=domain_code,
        main_pipe_code=main_pipe_code,
        # Inherited from the output this assembly decorates, so both key together.
        run_metadata=pipe_output.job_metadata.run_metadata if pipe_output.job_metadata else None,
        trace_events=trace_events,
    )
    if result.graph_spec is not None:
        pipe_output.graph_spec = result.graph_spec
    if result.graph_assembly_error is not None:
        pipe_output.graph_assembly_error = result.graph_assembly_error
    if result.tokens_usages is not None:
        pipe_output.tokens_usages = result.tokens_usages
    if result.usage_assembly_error is not None:
        pipe_output.usage_assembly_error = result.usage_assembly_error
