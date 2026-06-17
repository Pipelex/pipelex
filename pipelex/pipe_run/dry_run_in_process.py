"""In-process, in-memory graph-producing dry run against an already-open library.

`dry_run_pipe_in_process` is the in-process twin of `dry_run_pipeline`
(`pipelex.pipeline.dry_run_pipeline`): it dry-runs ONE pipe against a library the caller
already opened, never dispatches (even under a Temporal-enabled hub), and traces the graph
into an in-memory event log. It lives in its own module — not in `dry_run_pipeline` —
because `dry_run_pipeline` imports `PipelexMTHDSProtocol` from `pipelex.pipeline.runner`,
and the protocol's `validate` graph arm calls this function: sharing a module would close
an import cycle through `runner`.
"""

from polyfactory.exceptions import FactoryException

from pipelex import log
from pipelex.base_exceptions import PipelexError
from pipelex.cogt.content_generation.content_generator import ContentGenerator
from pipelex.config import get_config
from pipelex.core.pipes.pipe_abstract import PipeAbstract
from pipelex.graph.graph_tracer_manager import GraphTracerManager
from pipelex.graph.graphspec import GraphSpec
from pipelex.hub import get_library_manager, scoped_content_generator, scoped_event_log, scoped_pipe_router
from pipelex.observer.observer_protocol import ObserverNoOp
from pipelex.pipe_run.exceptions import DryRunGraphNotProducedError
from pipelex.pipe_run.pipe_router import PipeRouter
from pipelex.pipe_run.pipe_run import PipeRun
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.pipeline.execution_seams import prepare_pipe_job
from pipelex.pipeline.pipeline_factory import PipelineFactory
from pipelex.system.telemetry.otel_constants import OTelConstants
from pipelex.tracing.in_memory_event_log import InMemoryEventLog


async def best_effort_graph_spec(pipe_ref: str | None, *, library_id: str | None, log_context: str) -> GraphSpec | None:
    """Best-effort graph arm of the validate surfaces: dry-run ``pipe_ref`` for its graph, or degrade to None.

    The ONE implementation of the validate graph-arm contract, shared by every backend
    (`PipelexMTHDSProtocol.validate` and the Temporal validate activity) so they answer
    identically for the same bundle: no target or no library means no graph; pipe
    resolution targets the EXPLICIT ``library_id`` (never the ambient current-library
    contextvar — the caller captured the validation library once and the graph must come
    from that same library) and sits INSIDE the catch on purpose (an unknown ``pipe_ref``
    degrades like any other graph-arm domain failure); an expected dry-run domain
    failure — ``PipelexError``, polyfactory ``FactoryException``, or any ``ValueError``
    (covers pydantic ``ValidationError`` and the ValueError-family domain errors such as
    ``ConceptValueError``, all reachable from the mock-input mint and schema resolution) —
    degrades to ``None`` with a warning. Only non-Pipelex programming bugs propagate.

    Args:
        pipe_ref: The namespaced ref of the pipe to dry-run, or ``None`` for no graph.
        library_id: The id of the already-open library to run against, or ``None`` for no graph.
        log_context: Caller tag prefixed to the degrade warning (e.g. ``"act_dry_validate"``).

    Returns:
        The assembled GraphSpec, or ``None`` when skipped or degraded.
    """
    if not pipe_ref or not library_id:
        return None
    try:
        pipe = get_library_manager().get_library(library_id=library_id).pipe_library.get_required_pipe(pipe_code=pipe_ref)
        return await dry_run_pipe_in_process(pipe=pipe, library_id=library_id)
    except (PipelexError, FactoryException, ValueError) as graph_error:
        log.warning(
            f"{log_context}: graph dry-run of '{pipe_ref}' did not produce a graph "
            f"({type(graph_error).__name__}: {graph_error}); returning validation result without graph_spec"
        )
        return None


async def dry_run_pipe_in_process(pipe: PipeAbstract, *, library_id: str) -> GraphSpec:
    """Dry-run ``pipe`` against an already-open library fully in-process, tracing the graph in memory.

    The in-process twin of :func:`pipelex.pipeline.dry_run_pipeline.dry_run_pipeline` for hosts
    where the hub is Temporal-enabled but the run must NOT dispatch anything — e.g. the body of
    the dry-run/validation Temporal activity, or the protocol `validate` graph arm. Three
    contextvar scopes pin the whole run (root pipe + nested controller sub-pipes + inference
    leaves) to in-process execution:

    - ``scoped_event_log(InMemoryEventLog())`` — emit and assemble share one in-memory transport
      (no NDJSON file, no DynamoDB round-trip); the ``GraphSpec`` rides back on ``PipeOutput``.
    - ``scoped_pipe_router(local PipeRouter)`` — nested controller sub-pipes resolve the local
      router instead of the hub's ``TemporalPipeRouter`` (mirrors ``BundleValidator``).
    - ``scoped_content_generator(inline ContentGenerator)`` — inference leaves resolve an inline
      generator instead of the hub's ``ContentGeneratorInWorkflow``, so nothing dispatches; the
      DRY mock lives at the cogt leaf (Part B), which also skips all storage IO.

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
        DryRunGraphNotProducedError: If the dry-run completes without producing a graph spec.
    """
    execution_config = get_config().pipelex.pipeline_execution_config.with_execution_overrides(
        generate_graph=True,
        mock_inputs=True,
    )
    pipeline_run_id = f"dry_run_graph_{PipelineFactory.make_pipeline_run_id()}"
    event_log = InMemoryEventLog()

    # Local, direct execution primitives — NOT get_pipe_run() (a Temporal hub would spawn a
    # workflow). Keep the router instance: the scope installs it for nested sub-pipes.
    # Constructed BEFORE the tracer opens so nothing can raise between open_tracer and the
    # try/finally that guarantees its close — an entry in the process-wide GraphTracerManager
    # must never outlive this call.
    pipe_router = PipeRouter(observer=ObserverNoOp())
    pipe_run = PipeRun(pipe_router=pipe_router)
    content_generator = ContentGenerator.make_inline()

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
    try:
        with scoped_event_log(event_log), scoped_pipe_router(pipe_router), scoped_content_generator(content_generator):
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
        raise DryRunGraphNotProducedError(msg)

    return pipe_output.graph_spec
