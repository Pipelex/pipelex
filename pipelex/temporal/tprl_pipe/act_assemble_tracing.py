"""Temporal activity for assembling tracing artifacts from the trace-event stream.

Reads trace events from the configured backend (DynamoDB / NDJSON) once and
assembles the full GraphSpec (for ``--graph``) and the aggregated token usage
(for ``--costs``). Runs as an activity because backend reads are I/O that cannot
happen inside a workflow thread.
"""

from pydantic import BaseModel
from temporalio import activity

from pipelex.pipe_run.tracing_assembly import TracingAssembly, assemble_tracing


class AssembleTracingArg(BaseModel):
    """Input for the tracing assembly activity."""

    pipeline_run_id: str
    domain_code: str | None = None
    main_pipe_code: str | None = None
    # Which artifacts to assemble (mirror of the run's GraphContext emit flags). The submitter gates
    # the dispatch on these too; passing them through keeps the activity a pure function of its input.
    assemble_graph: bool = True
    assemble_usage: bool = True


# NOT decorated with @convert_pipelex_errors: tracing assembly is observability, not a pipe step.
# `assemble_tracing` already catches the EXPECTED best-effort failures (backend read errors, malformed
# events, broken tracing infra) and returns them on the *_assembly_error fields — those never raise here.
# A genuinely unexpected error (a programming bug in assembly) is deliberately allowed to propagate so the
# activity fails and `WfPipeRun` records it on usage_assembly_error / graph_assembly_error (its existing
# `except ActivityError` branch), mirroring DIRECT mode where assemble_tracing_on_output lets the same
# errors surface. Swallowing them here would make the workflow see success and silently produce no cost
# report and no diagnostic. The plain ActivityError carries the message WfPipeRun stringifies; no
# ErrorReport classification is needed for an observability artifact.
@activity.defn(name="act_assemble_tracing")
async def act_assemble_tracing(arg: AssembleTracingArg) -> TracingAssembly:  # noqa: RUF029
    """Read trace events and assemble graph + usage.

    Returns an empty result when no events are found or tracing is disabled. Expected best-effort
    failures are caught inside :func:`assemble_tracing` and returned on the ``*_assembly_error`` fields;
    unexpected errors propagate so the workflow surfaces them (see the module-level note above).
    """
    return assemble_tracing(
        pipeline_run_id=arg.pipeline_run_id,
        assemble_graph=arg.assemble_graph,
        assemble_usage=arg.assemble_usage,
        domain_code=arg.domain_code,
        main_pipe_code=arg.main_pipe_code,
    )
