"""Pipeline-level dry run with graph generation.

Provides a single entrypoint to dry-run an entire pipeline from MTHDS content,
producing a GraphSpec. Used by both the CLI graph commands and the API.
"""

from pipelex.base_exceptions import PipelexError
from pipelex.cogt.content_generation.content_generator_dry import ContentGeneratorDry
from pipelex.config import get_config
from pipelex.core.interpreter.exceptions import PipelexInterpreterError
from pipelex.core.interpreter.interpreter import PipelexInterpreter
from pipelex.core.pipes.pipe_abstract import PipeAbstract
from pipelex.core.pipes.pipe_factory import PipeFactory
from pipelex.graph.graph_tracer_manager import GraphTracerManager
from pipelex.graph.graphspec import GraphSpec
from pipelex.hub import scoped_content_generator, scoped_event_log, scoped_pipe_router
from pipelex.observer.observer_protocol import ObserverNoOp
from pipelex.pipe_run.pipe_router import PipeRouter
from pipelex.pipe_run.pipe_run import PipeRun
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.pipeline.execution_seams import prepare_pipe_job
from pipelex.pipeline.pipeline_factory import PipelineFactory
from pipelex.pipeline.runner import PipelexRunner
from pipelex.system.telemetry.otel_constants import OTelConstants
from pipelex.tracing.in_memory_event_log import InMemoryEventLog


async def dry_run_pipeline(
    mthds_contents: list[str] | None = None,
    bundle_uris: list[str] | None = None,
    library_dirs: list[str] | None = None,
) -> tuple[GraphSpec, str]:
    """Dry-run a full pipeline from MTHDS content, producing a GraphSpec.

    Parses the content, identifies the main pipe, and executes the pipeline
    in dry-run mode with graph tracing enabled and mock inputs.

    All contents are parsed into blueprints and loaded together; the main_pipe
    is found from the first blueprint that declares one.

    Args:
        mthds_contents: List of MTHDS bundle contents as strings.
        bundle_uris: Optional list of URIs for the bundles (used by runner for dedup).
        library_dirs: Optional library directories for pipe resolution.

    Returns:
        Tuple of (GraphSpec, pipe_code).

    Raises:
        PipelexInterpreterError: If content parsing fails or main_pipe is missing.
        PipelexError: If pipeline execution does not produce a graph spec.
        PipelineExecutionError: If dry-run execution fails.
    """
    if not mthds_contents:
        msg = "mthds_contents must be provided"
        raise ValueError(msg)

    # Pre-parse contents to extract main_pipe_code.
    # Note: pipeline_run_setup will re-parse these contents. The double-parse is
    # accepted because the runner interface requires pipe_code upfront and does not
    # expose the internally-resolved pipe code in its response.
    main_pipe_code: str | None = None

    for content in mthds_contents:
        bundle_blueprint = PipelexInterpreter.make_pipelex_bundle_blueprint(mthds_content=content)
        if bundle_blueprint.main_pipe and main_pipe_code is None:
            # Domain-qualify to avoid ambiguity across multiple domains
            main_pipe_code = PipeFactory.make_pipe_ref_with_domain(domain_code=bundle_blueprint.domain, pipe_code=bundle_blueprint.main_pipe)

    if not main_pipe_code:
        msg = "Bundle does not declare a main_pipe, cannot generate graph"
        raise PipelexInterpreterError(msg)

    pipe_code: str = main_pipe_code

    execution_config = get_config().pipelex.pipeline_execution_config.with_execution_overrides(
        generate_graph=True,
        mock_inputs=True,
    )

    runner = PipelexRunner(
        bundle_uris=bundle_uris,
        pipe_run_mode=PipeRunMode.DRY,
        execution_config=execution_config,
        library_dirs=library_dirs or [],
    )
    response = await runner.execute_pipeline(
        pipe_code=pipe_code,
        mthds_contents=mthds_contents,
    )
    pipe_output = response.pipe_output

    if not pipe_output.graph_spec:
        msg = "Pipeline execution did not produce a graph spec"
        raise PipelexError(msg)

    return pipe_output.graph_spec, pipe_code


async def dry_run_pipe_in_process(pipe: PipeAbstract, *, library_id: str) -> GraphSpec:
    """Dry-run ``pipe`` against an already-open library fully in-process, tracing the graph in memory.

    The in-process twin of :func:`dry_run_pipeline` for hosts where the hub is Temporal-enabled
    but the run must NOT dispatch anything — e.g. the body of the dry-run/validation Temporal
    activity. Three contextvar scopes pin the whole run (root pipe + nested controller sub-pipes
    + inference leaves) to in-process execution:

    - ``scoped_event_log(InMemoryEventLog())`` — emit and assemble share one in-memory transport
      (no NDJSON file, no DynamoDB round-trip); the ``GraphSpec`` rides back on ``PipeOutput``.
    - ``scoped_pipe_router(local PipeRouter)`` — nested controller sub-pipes resolve the local
      router instead of the hub's ``TemporalPipeRouter`` (mirrors ``BundleValidator``).
    - ``scoped_content_generator(ContentGeneratorDry())`` — inference leaves resolve the inline
      dry generator instead of the hub's ``ContentGeneratorInWorkflow``, so the in-process
      guarantee holds regardless of where the DRY mock lives (pipe level today, leaf level after
      Part B).

    The tracer is opened at ``graph_id=pipeline_run_id`` and closed by ``pipeline_run_id`` (in
    ``PipeRun.run``'s ``finally``) — emit and assemble keys are aligned by construction (D-C7).
    Usage/cost events are not emitted (``emit_usage_events=False``): this is a validation-side
    dry-run, not a billed run.

    The caller owns the library lifecycle: ``library_id`` must be open and current, and is left
    untouched (mirrors ``BundleValidator.validate_pipes``).

    Args:
        pipe: The pipe to dry-run (resolved against the open library).
        library_id: The id of the already-open library to run against.

    Returns:
        The assembled GraphSpec.

    Raises:
        PipelexError: If the dry-run fails or did not produce a graph spec.
    """
    execution_config = get_config().pipelex.pipeline_execution_config.with_execution_overrides(
        generate_graph=True,
        mock_inputs=True,
    )
    pipeline_run_id = f"dry_run_graph_{PipelineFactory.make_pipeline_run_id()}"
    event_log = InMemoryEventLog()

    graph_tracer_manager = GraphTracerManager.get_or_create_instance()
    trace_context = graph_tracer_manager.open_tracer(
        graph_id=pipeline_run_id,
        data_inclusion=execution_config.graph_config.data_inclusion,
        pipeline_ref_domain=pipe.domain_code,
        pipeline_ref_main_pipe=pipe.code,
        event_log=event_log,
        workflow_id="direct",
        pipeline_run_id=pipeline_run_id,
        emit_graph_events=True,
        emit_usage_events=False,
    )

    # Local, direct execution primitive — NOT get_pipe_run() (a Temporal hub would spawn a
    # workflow). Keep the router instance: the scope installs it for nested sub-pipes.
    pipe_router = PipeRouter(observer=ObserverNoOp())
    pipe_run = PipeRun(pipe_router=pipe_router)
    try:
        with scoped_event_log(event_log), scoped_pipe_router(pipe_router), scoped_content_generator(ContentGeneratorDry()):
            pipe_job = await prepare_pipe_job(
                pipe=pipe,
                library_id=library_id,
                execution_config=execution_config,
                pipe_run_mode=PipeRunMode.DRY,
                pipeline_run_id=pipeline_run_id,
                user_id=OTelConstants.DEFAULT_USER_ID,
                trace_context=trace_context,
            )
            # PipeRun.run's finally closes the tracer by pipeline_run_id and assembles the
            # GraphSpec from the scoped in-memory log onto pipe_output.
            pipe_output = await pipe_run.run(pipe_job)
    finally:
        # Safety net for failures before PipeRun.run owns the tracer (e.g. prepare_pipe_job
        # raising): close_tracer pops by key, so this is a no-op after a completed run.
        graph_tracer_manager.close_tracer(pipeline_run_id)

    if not pipe_output.graph_spec:
        msg = f"In-process dry-run of pipe '{pipe.pipe_ref}' did not produce a graph spec"
        raise PipelexError(msg)

    return pipe_output.graph_spec
