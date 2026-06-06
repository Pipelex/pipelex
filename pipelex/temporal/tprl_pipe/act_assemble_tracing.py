"""Temporal activity for assembling tracing artifacts from the trace-event stream.

Reads trace events from the configured backend (DynamoDB / NDJSON) once and
assembles the full GraphSpec (for ``--graph``) and the aggregated token usage
(for ``--costs``). Runs as an activity because backend reads are I/O that cannot
happen inside a workflow thread.
"""

from pydantic import BaseModel
from temporalio import activity

from pipelex import log
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


# Deliberately NOT decorated with @convert_pipelex_errors: this activity is best-effort
# observability — it swallows every failure and degrades to an empty result, so no error ever
# crosses the boundary for the decorator to convert.
@activity.defn(name="act_assemble_tracing")
async def act_assemble_tracing(arg: AssembleTracingArg) -> TracingAssembly:  # noqa: RUF029
    """Read trace events and assemble graph + usage. Returns an empty result if no events found."""
    try:
        return assemble_tracing(
            pipeline_run_id=arg.pipeline_run_id,
            assemble_graph=arg.assemble_graph,
            assemble_usage=arg.assemble_usage,
            domain_code=arg.domain_code,
            main_pipe_code=arg.main_pipe_code,
        )
    except Exception as exc:  # noqa: BLE001
        # Temporal activity root: tracing assembly is best-effort observability — any unexpected failure
        # degrades to an empty result rather than failing the workflow (assemble_tracing already handles
        # the expected read/assemble exceptions internally).
        log.warning(f"Tracing assembly activity failed: {exc}")
        return TracingAssembly()
