"""Pipeline-level dry run with graph generation.

Provides a single entrypoint to dry-run an entire pipeline from MTHDS content,
producing a GraphSpec. Used by the CLI graph commands.

It lives at the pipeline altitude — it instantiates the protocol runner
(`PipelexMTHDSProtocol`) and runs a whole bundle — unlike its in-process twin
`dry_run_pipe_in_process` (`pipelex.pipe_run.dry_run_in_process`), which dry-runs ONE pipe
against an already-open library without dispatching. The twin's callers (the protocol
`validate` graph arm among them) cannot share a module with the runner import without a
cycle, which is why the two entrypoints are separate modules at separate altitudes.
"""

from pipelex.config import get_config
from pipelex.core.interpreter.exceptions import PipelexInterpreterError
from pipelex.core.interpreter.interpreter import PipelexInterpreter
from pipelex.graph.graphspec import GraphSpec
from pipelex.hub import scoped_event_log
from pipelex.pipe_run.exceptions import DryRunGraphNotProducedError
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.pipeline.blueprint_selection import select_primary_blueprint
from pipelex.pipeline.runner import PipelexMTHDSProtocol
from pipelex.tracing.in_memory_event_log import InMemoryEventLog


async def dry_run_pipeline(
    mthds_contents: list[str] | None = None,
    *,
    bundle_uris: list[str] | None = None,
    library_dirs: list[str] | None = None,
    pipe_code: str | None = None,
) -> tuple[GraphSpec, str]:
    """Dry-run a full pipeline from MTHDS content, producing a GraphSpec.

    Parses the content, identifies the requested or main pipe, and executes the
    pipeline in dry-run mode with graph tracing enabled and mock inputs.

    All contents are parsed into blueprints and loaded together; the main_pipe
    is found from the first blueprint that declares one.

    Args:
        mthds_contents: List of MTHDS bundle contents as strings.
        bundle_uris: Optional list of URIs for the bundles (used by runner for dedup).
        library_dirs: Optional library directories for pipe resolution.
        pipe_code: Optional explicit pipe target. When omitted, the first selected
            `main_pipe` remains the default. Bare and qualified refs are accepted
            according to the loaded pipe library's normal resolution rules.

    Returns:
        Tuple of (GraphSpec, domain-qualified main-pipe ref).

    Raises:
        PipelexInterpreterError: If content parsing fails or main_pipe is missing.
        DryRunGraphNotProducedError: If pipeline execution does not produce a graph spec.
        PipelineExecutionError: If dry-run execution fails.
    """
    if not mthds_contents:
        msg = "mthds_contents must be provided"
        raise ValueError(msg)

    # Pre-parse contents to extract the default main pipe's domain-qualified ref via the one
    # shared selection rule. Note: pipeline_run_setup will re-parse these contents. The
    # double-parse is accepted because the runner interface requires the pipe ref upfront
    # and does not expose the internally-resolved pipe ref in its response.
    blueprints = [PipelexInterpreter.make_pipelex_bundle_blueprint(mthds_content=content) for content in mthds_contents]
    pipe_ref = pipe_code or select_primary_blueprint(blueprints).main_pipe_ref

    if not pipe_ref:
        msg = "Bundle does not declare a main_pipe, cannot generate graph"
        raise PipelexInterpreterError(msg)

    execution_config = get_config().pipelex.pipeline_execution_config.with_execution_overrides(
        generate_graph=True,
        mock_inputs=True,
    )

    runner = PipelexMTHDSProtocol(
        bundle_uris=bundle_uris,
        pipe_run_mode=PipeRunMode.DRY,
        execution_config=execution_config,
        library_dirs=library_dirs or [],
    )
    # This function's whole purpose is the graph, so it owns the graph transport: the scoped
    # in-memory event log is the run's emit AND assemble channel (see hub.scoped_event_log, D1),
    # making graph generation independent of the host's tracing_config — a host with tracing
    # disabled (e.g. pipelex-api's /validate in direct mode) still gets its graph, and a host
    # with a configured backend doesn't get trace files written as a side effect of validation.
    with scoped_event_log(InMemoryEventLog()):
        response = await runner.execute(
            pipe_code=pipe_ref,
            mthds_contents=mthds_contents,
        )
    pipe_output = response.pipe_output

    if not pipe_output.graph_spec:
        msg = "Pipeline execution did not produce a graph spec"
        raise DryRunGraphNotProducedError(msg)

    resolved_pipe_ref = pipe_ref
    pipeline_ref = pipe_output.graph_spec.pipeline_ref
    if pipeline_ref.domain and pipeline_ref.main_pipe:
        resolved_pipe_ref = f"{pipeline_ref.domain}.{pipeline_ref.main_pipe}"

    return pipe_output.graph_spec, resolved_pipe_ref
